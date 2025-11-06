"""Worker process module for executing jobs"""

import subprocess
import time
import signal
import sys
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
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        print(f"\n[Worker {self.worker_id}] Received shutdown signal, finishing current job...")
        self.running = False
    
    def _calculate_backoff(self, attempts: int) -> float:
        """Calculate exponential backoff delay"""
        base = self.config.get("backoff_base", 2)
        return base ** attempts
    
    def _execute_command(self, command: str) -> Tuple[bool, str]:
        """Execute a shell command and return (success, error_message)"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            if result.returncode == 0:
                return True, ""
            else:
                error_msg = result.stderr.strip() or f"Command failed with exit code {result.returncode}"
                return False, error_msg
        except subprocess.TimeoutExpired:
            return False, "Command execution timeout (5 minutes)"
        except Exception as e:
            return False, str(e)
    
    def process_job(self, job: dict) -> bool:
        """Process a single job"""
        job_id = job['id']
        command = job['command']
        
        # Try to claim the job atomically
        if not self.storage.claim_job(job_id):
            # Job was already claimed by another worker
            return False
        
        self.current_job_id = job_id
        print(f"[Worker {self.worker_id}] Processing job {job_id}: {command}")
        
        # Execute the command
        success, error_message = self._execute_command(command)
        
        if success:
            self.storage.complete_job(job_id)
            print(f"[Worker {self.worker_id}] Job {job_id} completed successfully")
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
                # Move to DLQ
                self.storage.fail_job(job_id, error_message, should_retry=False)
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

