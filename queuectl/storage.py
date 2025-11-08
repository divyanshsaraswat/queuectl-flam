"""Job storage and persistence module using SQLite"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict
from filelock import FileLock


class DuplicateJobError(Exception):
    """Exception raised when trying to create a job with an ID that already exists"""
    pass


class JobStorage:
    """Manages job persistence using SQLite database"""
    
    def __init__(self, db_path: str = "queuectl.db"):
        self.db_path = db_path
        self.lock_path = f"{db_path}.lock"
        self.lock = FileLock(self.lock_path, timeout=10)
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_retry_at TEXT,
                    error_message TEXT,
                    priority INTEGER DEFAULT 0,
                    timeout INTEGER DEFAULT NULL,
                    run_at TEXT DEFAULT NULL,
                    output_logs TEXT DEFAULT NULL,
                    execution_time REAL DEFAULT NULL,
                    started_at TEXT DEFAULT NULL,
                    completed_at TEXT DEFAULT NULL
                )
            """)
            # Add new columns if they don't exist (for existing databases)
            existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()]
            columns_to_add = {
                'priority': 'INTEGER DEFAULT 0',
                'timeout': 'INTEGER',
                'run_at': 'TEXT',
                'output_logs': 'TEXT',
                'execution_time': 'REAL',
                'started_at': 'TEXT',
                'completed_at': 'TEXT'
            }
            for column, column_type in columns_to_add.items():
                if column not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {column_type}")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
            conn.commit()
            conn.close()
    
    def create_job(self, job_id: str, command: str, max_retries: int = 3, 
                   priority: int = 0, timeout: Optional[int] = None, 
                   run_at: Optional[str] = None) -> Dict:
        """Create a new job
        
        Raises:
            DuplicateJobError: If a job with the same ID already exists
        """
        now = datetime.utcnow().isoformat() + "Z"
        job = {
            "id": job_id,
            "command": command,
            "state": "pending",
            "attempts": 0,
            "max_retries": max_retries,
            "created_at": now,
            "updated_at": now,
            "priority": priority,
            "timeout": timeout,
            "run_at": run_at
        }
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Check if job with this ID already exists (within the same lock)
                cursor.execute("SELECT id, state FROM jobs WHERE id = ?", (job_id,))
                existing_row = cursor.fetchone()
                if existing_row:
                    conn.close()
                    raise DuplicateJobError(f"Job with ID '{job_id}' already exists. Current state: {existing_row[1]}")
                
                # Insert the new job
                cursor.execute("""
                    INSERT INTO jobs (id, command, state, attempts, max_retries, created_at, updated_at, 
                                     priority, timeout, run_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (job_id, command, "pending", 0, max_retries, now, now, priority, timeout, run_at))
                conn.commit()
            except sqlite3.IntegrityError:
                # Fallback: In case of race condition (though unlikely due to lock)
                # Query the existing job state
                cursor.execute("SELECT id, state FROM jobs WHERE id = ?", (job_id,))
                existing_row = cursor.fetchone()
                if existing_row:
                    conn.close()
                    raise DuplicateJobError(f"Job with ID '{job_id}' already exists. Current state: {existing_row[1]}")
                else:
                    conn.close()
                    raise
            finally:
                conn.close()
        
        return job
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get a job by ID"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
    
    def get_pending_jobs(self) -> List[Dict]:
        """Get all pending jobs ready for processing, ordered by priority and run_at"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get current UTC time in ISO format for comparison
            now_utc = datetime.utcnow().isoformat() + "Z"
            
            # SQLite can compare ISO format strings directly, but we need to ensure
            # we're comparing UTC times. Since next_retry_at is stored in UTC (ISO with Z),
            # we compare it with current UTC time
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE state = 'pending' 
                AND (next_retry_at IS NULL OR next_retry_at <= ?)
                AND (run_at IS NULL OR run_at <= ?)
                ORDER BY priority DESC, 
                         CASE WHEN run_at IS NULL THEN 1 ELSE 0 END,
                         run_at ASC, 
                         created_at ASC
            """, (now_utc, now_utc))
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
    
    def get_jobs_by_state(self, state: str) -> List[Dict]:
        """Get all jobs with a specific state"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC", (state,))
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
    
    def claim_job(self, job_id: str) -> bool:
        """Atomically claim a job for processing (prevent duplicate processing)"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat() + "Z"
            cursor.execute("""
                UPDATE jobs 
                SET state = 'processing', updated_at = ?, started_at = ?
                WHERE id = ? AND state = 'pending'
            """, (now, now, job_id))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success
    
    def complete_job(self, job_id: str, execution_time: Optional[float] = None, 
                     output_logs: Optional[str] = None):
        """Mark a job as completed"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat() + "Z"
            cursor.execute("""
                UPDATE jobs 
                SET state = 'completed', updated_at = ?, completed_at = ?,
                    execution_time = COALESCE(?, execution_time),
                    output_logs = COALESCE(?, output_logs)
                WHERE id = ?
            """, (now, now, execution_time, output_logs, job_id))
            conn.commit()
            conn.close()
    
    def fail_job(self, job_id: str, error_message: str, should_retry: bool, next_retry_at: Optional[str] = None):
        """Mark a job as failed and either schedule retry or move to DLQ"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            job = self.get_job(job_id)
            if not job:
                conn.close()
                return
            
            new_attempts = job['attempts'] + 1
            
            if should_retry and new_attempts <= job['max_retries']:
                # Schedule retry - set back to pending state
                cursor.execute("""
                    UPDATE jobs 
                    SET state = 'pending', attempts = ?, updated_at = ?, 
                        next_retry_at = ?, error_message = ?
                    WHERE id = ?
                """, (new_attempts, datetime.utcnow().isoformat() + "Z", next_retry_at, error_message, job_id))
            else:
                # Move to DLQ
                cursor.execute("""
                    UPDATE jobs 
                    SET state = 'dead', attempts = ?, updated_at = ?, error_message = ?
                    WHERE id = ?
                """, (new_attempts, datetime.utcnow().isoformat() + "Z", error_message, job_id))
            
            conn.commit()
            conn.close()
    
    def reset_job_for_retry(self, job_id: str):
        """Reset a DLQ job for retry"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs 
                SET state = 'pending', attempts = 0, next_retry_at = NULL, 
                    error_message = NULL, updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat() + "Z", job_id))
            conn.commit()
            conn.close()
    
    def get_stats(self) -> Dict:
        """Get statistics about all jobs"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            stats = {}
            for state in ['pending', 'processing', 'completed', 'failed', 'dead']:
                cursor.execute("SELECT COUNT(*) FROM jobs WHERE state = ?", (state,))
                stats[state] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM jobs")
            stats['total'] = cursor.fetchone()[0]
            
            # Execution metrics
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_completed,
                    AVG(execution_time) as avg_execution_time,
                    MIN(execution_time) as min_execution_time,
                    MAX(execution_time) as max_execution_time,
                    SUM(CASE WHEN execution_time IS NOT NULL THEN 1 ELSE 0 END) as jobs_with_timing
                FROM jobs 
                WHERE state = 'completed'
            """)
            row = cursor.fetchone()
            if row and row[0]:
                stats['execution_metrics'] = {
                    'total_completed': row[0],
                    'avg_execution_time': row[1] if row[1] else 0,
                    'min_execution_time': row[2] if row[2] else 0,
                    'max_execution_time': row[3] if row[3] else 0,
                    'jobs_with_timing': row[4]
                }
            else:
                stats['execution_metrics'] = {
                    'total_completed': 0,
                    'avg_execution_time': 0,
                    'min_execution_time': 0,
                    'max_execution_time': 0,
                    'jobs_with_timing': 0
                }
            
            # Success rate
            cursor.execute("SELECT COUNT(*) FROM jobs WHERE state = 'completed'")
            completed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('completed', 'failed', 'dead')")
            finished = cursor.fetchone()[0]
            stats['success_rate'] = (completed / finished * 100) if finished > 0 else 0
            
            conn.close()
            return stats

