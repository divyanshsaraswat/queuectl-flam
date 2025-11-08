"""Worker process module for executing jobs"""

import subprocess
import time
import signal
import sys
import platform
from datetime import datetime, timedelta
from typing import Optional, Tuple
from .storage import JobStorage
from .config import Config


class Worker:
    """Worker process that executes jobs"""
    
    def __init__(self, worker_id: int, storage: JobStorage, config: Config):
        self.worker_id = worker_id
        self.storage = storage
        self.config = config
        self.running = False
        self.current_job_id: Optional[str] = None
        
        # Setup signal handlers for graceful shutdown (cross-platform)
        if platform.system() != 'Windows':
            # Unix/Linux/Mac: Use SIGINT and SIGTERM
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        else:
            # Windows: Only SIGINT is available, SIGBREAK is Windows-specific
            signal.signal(signal.SIGINT, self._signal_handler)
            if hasattr(signal, 'SIGBREAK'):
                signal.signal(signal.SIGBREAK, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\n[Worker {self.worker_id}] Received shutdown signal, finishing current job...")
        self.running = False
    
    def _calculate_backoff(self, attempts: int) -> float:
        """Calculate exponential backoff delay"""
        base = self.config.get("backoff_base", 2)
        return base ** attempts
    
    def _execute_command(self, command: str, timeout: Optional[int] = None) -> Tuple[bool, str, str]:
        """Execute a shell command and return (success, error_message, output_logs)"""
        default_timeout = self.config.get("default_timeout", 300)  # Configurable default timeout
        actual_timeout = timeout if timeout is not None else default_timeout
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=actual_timeout
            )
            
            # Combine stdout and stderr for logging
            output_logs = ""
            if result.stdout:
                output_logs += f"STDOUT:\n{result.stdout}\n"
            if result.stderr:
                output_logs += f"STDERR:\n{result.stderr}\n"
            
            if result.returncode == 0:
                return True, "", output_logs.strip()
            else:
                error_msg = result.stderr.strip() or f"Command failed with exit code {result.returncode}"
                return False, error_msg, output_logs.strip()
        except subprocess.TimeoutExpired:
            timeout_msg = f"Command execution timeout ({actual_timeout} seconds)"
            return False, timeout_msg, f"STDERR:\n{timeout_msg}\n"
        except Exception as e:
            error_msg = str(e)
            return False, error_msg, f"STDERR:\n{error_msg}\n"
    
    def process_job(self, job: dict) -> bool:
        """Process a single job"""
        job_id = job['id']
        command = job['command']
        timeout = job.get('timeout')
        
        # Try to claim the job atomically
        if not self.storage.claim_job(job_id):
            # Job was already claimed by another worker
            return False
        
        self.current_job_id = job_id
        print(f"[Worker {self.worker_id}] Processing job {job_id}: {command}")
        if timeout:
            print(f"[Worker {self.worker_id}] Job {job_id} timeout: {timeout} seconds")
        
        # Track execution time
        start_time = time.time()
        
        # Execute the command
        success, error_message, output_logs = self._execute_command(command, timeout)
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        if success:
            self.storage.complete_job(job_id, execution_time=execution_time, output_logs=output_logs)
            print(f"[Worker {self.worker_id}] Job {job_id} completed successfully in {execution_time:.2f}s")
            self.current_job_id = None
            return True
        else:
            # Job failed - calculate retry
            attempts = job['attempts']
            max_retries = job.get('max_retries', self.config.get("max_retries", 3))
            
            if attempts < max_retries:
                # Schedule retry with exponential backoff
                # Use attempts + 1 for backoff calculation (after this failure, attempts will be attempts + 1)
                delay_seconds = self._calculate_backoff(attempts + 1)
                next_retry_at = (datetime.utcnow() + timedelta(seconds=delay_seconds)).isoformat() + "Z"
                
                # Reset to pending state for retry
                self.storage.fail_job(job_id, error_message, should_retry=True, next_retry_at=next_retry_at)
                print(f"[Worker {self.worker_id}] Job {job_id} failed (attempt {attempts + 1}/{max_retries}). "
                      f"Retrying in {delay_seconds:.1f} seconds. Error: {error_message}")
            else:
                # Move to DLQ - also save output logs for failed jobs
                self.storage.fail_job(job_id, error_message, should_retry=False)
                # Update output logs for failed job
                with self.storage.lock:
                    import sqlite3
                    conn = sqlite3.connect(self.storage.db_path)
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE jobs 
                        SET output_logs = ?, execution_time = ?
                        WHERE id = ?
                    """, (output_logs, execution_time, job_id))
                    conn.commit()
                    conn.close()
                print(f"[Worker {self.worker_id}] Job {job_id} exhausted retries. Moved to DLQ. Error: {error_message}")
            
            self.current_job_id = None
            return True
    
    def run(self):
        """Main worker loop"""
        self.running = True
        print(f"[Worker {self.worker_id}] Started")
        
        while self.running:
            try:
                # Get pending jobs
                pending_jobs = self.storage.get_pending_jobs()
                
                if pending_jobs:
                    # Process the first available job
                    for job in pending_jobs:
                        if not self.running:
                            break
                        self.process_job(job)
                        break  # Process one job per iteration
                else:
                    # No jobs available, sleep briefly
                    time.sleep(0.5)
            
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"[Worker {self.worker_id}] Error: {e}")
                time.sleep(1)
        
        # Finish current job if any
        if self.current_job_id:
            print(f"[Worker {self.worker_id}] Finishing current job {self.current_job_id}...")
            # Wait a bit for the job to complete
            time.sleep(2)
        
        print(f"[Worker {self.worker_id}] Stopped")

