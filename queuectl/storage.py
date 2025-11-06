"""Job storage and persistence module using SQLite"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict
from filelock import FileLock


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
                    error_message TEXT
                )
            """)
            conn.commit()
            conn.close()
    
    def create_job(self, job_id: str, command: str, max_retries: int = 3) -> Dict:
        """Create a new job"""
        now = datetime.utcnow().isoformat() + "Z"
        job = {
            "id": job_id,
            "command": command,
            "state": "pending",
            "attempts": 0,
            "max_retries": max_retries,
            "created_at": now,
            "updated_at": now
        }
        
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (id, command, state, attempts, max_retries, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (job_id, command, "pending", 0, max_retries, now, now))
            conn.commit()
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
        """Get all pending jobs ready for processing"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE state = 'pending' 
                AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
                ORDER BY created_at ASC
            """)
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
            cursor.execute("""
                UPDATE jobs 
                SET state = 'processing', updated_at = ?
                WHERE id = ? AND state = 'pending'
            """, (datetime.utcnow().isoformat() + "Z", job_id))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return success
    
    def complete_job(self, job_id: str):
        """Mark a job as completed"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE jobs 
                SET state = 'completed', updated_at = ?
                WHERE id = ?
            """, (datetime.utcnow().isoformat() + "Z", job_id))
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
            
            conn.close()
            return stats

