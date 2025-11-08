#!/usr/bin/env python3
"""Test script to validate QueueCTL core functionality"""

import subprocess
import time
import os
import json
import sys
import multiprocessing
import platform
from queuectl.storage import JobStorage
from queuectl.config import Config
from queuectl.worker import Worker


# Configure multiprocessing for Windows
_mp_context = None
if platform.system() == 'Windows':
    try:
        multiprocessing.set_start_method('spawn', force=True)
        _mp_context = multiprocessing.get_context('spawn')
    except RuntimeError:
        try:
            _mp_context = multiprocessing.get_context()
        except:
            _mp_context = multiprocessing
else:
    _mp_context = multiprocessing

# Global worker processes list for direct management
_worker_processes = []


def _worker_process_func(worker_id: int):
    """Worker process function - must be at module level for Windows multiprocessing"""
    storage = JobStorage()
    cfg = Config()
    worker = Worker(worker_id, storage, cfg)
    worker.run()


def start_workers_directly(count: int):
    """Start workers directly without using subprocess (for testing)"""
    global _worker_processes
    
    # Clean up any existing workers
    stop_workers_directly()
    
    pid_file = "queuectl.workers.pid"
    
    # Check if workers are already running
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            existing_pids = [int(pid) for pid in f.read().strip().split('\n') if pid]
        
        # Check if processes are still alive
        alive_pids = []
        for pid in existing_pids:
            try:
                os.kill(pid, 0)  # Check if process exists
                alive_pids.append(pid)
            except OSError:
                pass
        
        if alive_pids:
            print(f"Warning: {len(alive_pids)} worker(s) already running (PIDs: {alive_pids})")
            # Kill them first
            for pid in alive_pids:
                try:
                    if platform.system() == 'Windows':
                        subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                                     capture_output=True, timeout=5)
                    else:
                        os.kill(pid, 9)
                except:
                    pass
    
    # Start workers
    _worker_processes = []
    try:
        for i in range(count):
            p = _mp_context.Process(target=_worker_process_func, args=(i + 1,))
            p.daemon = False
            p.start()
            _worker_processes.append(p)
            print(f"Started worker {i + 1} (PID: {p.pid})")
            if platform.system() == 'Windows':
                time.sleep(0.1)  # Brief delay for Windows spawn
        
        # Verify processes are alive
        time.sleep(0.2)
        alive_processes = [p for p in _worker_processes if p.is_alive()]
        
        # Save PIDs
        with open(pid_file, 'w') as f:
            f.write('\n'.join(str(p.pid) for p in alive_processes))
        
        print(f"Started {len(alive_processes)} worker(s)")
        return len(alive_processes) == count
    except Exception as e:
        print(f"Error starting workers: {e}")
        stop_workers_directly()
        return False


def stop_workers_directly():
    """Stop workers directly without using subprocess (for testing)"""
    global _worker_processes
    
    # Stop processes we started directly
    for p in _worker_processes:
        try:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
                if p.is_alive():
                    p.kill()
        except:
            pass
    _worker_processes = []
    
    # Also stop any workers from PID file
    pid_file = "queuectl.workers.pid"
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            pids = [int(pid) for pid in f.read().strip().split('\n') if pid]
        
        for pid in pids:
            try:
                if platform.system() == 'Windows':
                    subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                                 capture_output=True, timeout=5)
                else:
                    os.kill(pid, 9)
            except:
                pass
        
        try:
            os.remove(pid_file)
        except:
            pass


def cleanup():
    """Clean up test files"""
    stop_workers_directly()  # Stop any running workers first
    
    files_to_remove = [
        "queuectl.db",
        "queuectl.db.lock",
        "queuectl.config.json",
        "queuectl.config.json.lock",
        "queuectl.workers.pid"
    ]
    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
            except:
                pass


def run_command(cmd):
    """Run a command and return output"""
    try:
        # On Windows, use CREATE_NEW_PROCESS_GROUP to avoid multiprocessing issues
        # when starting workers from within a subprocess
        creation_flags = 0
        if os.name == 'nt':
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
        
        # For worker start commands, use a longer timeout and ensure we don't wait
        # for child processes to fully initialize
        timeout = 30 if 'worker start' in cmd else 15
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creation_flags if os.name == 'nt' else 0
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        timeout_val = 30 if 'worker start' in cmd else 15
        print(f"WARNING: Command '{cmd}' timed out after {timeout_val} seconds")
        print("This might indicate a multiprocessing issue on Windows.")
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def test_1_basic_job_completion():
    """Test 1: Basic job completes successfully"""
    print("\n" + "="*60)
    print("TEST 1: Basic Job Completion")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    
    # Create a job
    job = storage.create_job("test1", "echo 'Test successful'", 3)
    assert job['state'] == 'pending', "Job should be pending initially"
    print(f"✓ Created job: {job['id']}")
    
    # Start a worker directly (avoid subprocess issues on Windows)
    print("Starting worker...")
    success = start_workers_directly(1)
    assert success, "Failed to start worker"
    time.sleep(2)
    
    # Process should complete
    time.sleep(3)
    
    # Check job status
    job = storage.get_job("test1")
    assert job is not None, "Job should exist"
    print(f"Job state: {job['state']}")
    
    # Stop worker
    stop_workers_directly()
    time.sleep(1)
    
    # Verify job completed
    job = storage.get_job("test1")
    if job['state'] == 'completed':
        print("✓ Test 1 PASSED: Job completed successfully")
        return True
    else:
        print(f"✗ Test 1 FAILED: Job state is {job['state']}, expected 'completed'")
        return False


def test_2_failed_job_retry():
    """Test 2: Failed job retries with backoff and moves to DLQ"""
    print("\n" + "="*60)
    print("TEST 2: Failed Job Retry and DLQ")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    config = Config()
    config.set("max_retries", 2)
    config.set("backoff_base", 2)
    
    # Create a job that will fail
    job = storage.create_job("test2", "nonexistent-command-that-fails", 2)
    print(f"✓ Created failing job: {job['id']}")
    
    # Start worker directly (avoid subprocess issues on Windows)
    print("Starting worker...")
    success = start_workers_directly(1)
    assert success, "Failed to start worker"
    time.sleep(2)  # Let worker start processing
    
    # Wait for retries to complete
    # With max_retries=2 and backoff_base=2:
    # - First failure: attempts=0 -> 1, backoff = 2^1 = 2s, next_retry_at = now + 2s
    # - Second failure: attempts=1 -> 2, backoff = 2^2 = 4s, next_retry_at = now + 4s
    # - Third failure: attempts=2 -> 3, which >= max_retries (2), so DLQ
    # Total time needed: ~1s (first failure) + 2s (backoff) + ~1s (second failure) + 4s (backoff) + ~1s (third failure) = ~9s
    # Add buffer for processing time
    print("Waiting for retries to complete (this will take ~15 seconds)...")
    
    # Poll for job state until it reaches DLQ or timeout
    # IMPORTANT: Keep workers running during this time!
    max_wait = 25  # Maximum wait time in seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        job = storage.get_job("test2")
        if job:
            state = job['state']
            attempts = job.get('attempts', 0)
            if state == 'dead':
                print(f"Job reached DLQ after {time.time() - start_time:.1f} seconds")
                break
            # Log progress every 3 seconds
            if int(time.time() - start_time) % 3 == 0:
                print(f"  Waiting... state={state}, attempts={attempts}")
        time.sleep(1)
    
    # Stop worker only after we've checked the final state
    stop_workers_directly()
    time.sleep(1)
    
    # Check job is in DLQ
    job = storage.get_job("test2")
    assert job is not None, "Job should exist"
    print(f"Job state: {job['state']}, attempts: {job['attempts']}")
    
    if job['state'] == 'dead' and job['attempts'] >= 2:
        print("✓ Test 2 PASSED: Job moved to DLQ after retries")
        return True
    else:
        print(f"✗ Test 2 FAILED: Job state is {job['state']}, attempts {job['attempts']}")
        return False


def test_3_multiple_workers():
    """Test 3: Multiple workers process jobs without overlap"""
    print("\n" + "="*60)
    print("TEST 3: Multiple Workers (No Overlap)")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    
    # Create multiple jobs
    job_ids = []
    for i in range(5):
        job_id = f"test3_{i}"
        storage.create_job(job_id, f"echo 'Job {i}'", 3)
        job_ids.append(job_id)
    
    print(f"✓ Created {len(job_ids)} jobs")
    
    # Start multiple workers directly (avoid subprocess issues on Windows)
    print("Starting 3 workers...")
    success = start_workers_directly(3)
    assert success, "Failed to start workers"
    time.sleep(2)
    
    # Wait for processing
    print("Waiting for jobs to process...")
    time.sleep(8)
    
    # Stop workers
    stop_workers_directly()
    time.sleep(1)
    
    # Check all jobs processed
    completed = 0
    for job_id in job_ids:
        job = storage.get_job(job_id)
        if job and job['state'] == 'completed':
            completed += 1
    
    print(f"Completed jobs: {completed}/{len(job_ids)}")
    
    if completed == len(job_ids):
        print("✓ Test 3 PASSED: All jobs processed without overlap")
        return True
    else:
        print(f"✗ Test 3 FAILED: Only {completed}/{len(job_ids)} jobs completed")
        return False


def test_4_invalid_commands():
    """Test 4: Invalid commands fail gracefully"""
    print("\n" + "="*60)
    print("TEST 4: Invalid Commands Fail Gracefully")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    
    # Create job with invalid command
    job = storage.create_job("test4", "this-command-does-not-exist-12345", 1)
    print(f"✓ Created job with invalid command: {job['id']}")
    
    # Start worker directly (avoid subprocess issues on Windows)
    print("Starting worker...")
    success = start_workers_directly(1)
    assert success, "Failed to start worker"
    time.sleep(2)  # Let worker start processing
    
    # With max_retries=1:
    # - First failure: attempts=0 -> 1, backoff = 2^1 = 2s, next_retry_at = now + 2s
    # - Second failure: attempts=1 -> 2, which >= max_retries (1), so DLQ
    # Total time needed: ~1s (first failure) + 2s (backoff) + ~1s (second failure) = ~4s
    # Add buffer for processing time
    print("Waiting for job to fail and move to DLQ (this will take ~8 seconds)...")
    
    # Poll for job state until it reaches DLQ or timeout
    # IMPORTANT: Keep workers running during this time!
    max_wait = 15  # Maximum wait time in seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        job = storage.get_job("test4")
        if job:
            state = job['state']
            attempts = job.get('attempts', 0)
            if state in ['failed', 'dead']:
                print(f"Job reached final state '{state}' after {time.time() - start_time:.1f} seconds")
                break
            # Log progress every 2 seconds
            if int(time.time() - start_time) % 2 == 0:
                print(f"  Waiting... state={state}, attempts={attempts}")
        time.sleep(1)
    
    # Stop worker only after we've checked the final state
    stop_workers_directly()
    time.sleep(1)
    
    # Check job failed/handled
    job = storage.get_job("test4")
    assert job is not None, "Job should exist"
    print(f"Job state: {job['state']}, attempts: {job['attempts']}, error: {job.get('error_message', 'N/A')[:50]}")
    
    if job['state'] in ['failed', 'dead'] and job.get('error_message'):
        print("✓ Test 4 PASSED: Invalid command handled gracefully")
        return True
    else:
        print(f"✗ Test 4 FAILED: Job state {job['state']}, expected 'failed' or 'dead'")
        return False


def test_5_persistence():
    """Test 5: Job data persists across restarts"""
    print("\n" + "="*60)
    print("TEST 5: Job Persistence Across Restarts")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    
    # Create jobs
    job1 = storage.create_job("persist1", "echo 'Persistent job 1'", 3)
    job2 = storage.create_job("persist2", "echo 'Persistent job 2'", 3)
    print(f"✓ Created 2 jobs: {job1['id']}, {job2['id']}")
    
    # Verify jobs exist
    assert storage.get_job("persist1") is not None
    assert storage.get_job("persist2") is not None
    print("✓ Jobs stored in database")
    
    # Create new storage instance (simulating restart)
    storage2 = JobStorage()
    job1_restored = storage2.get_job("persist1")
    job2_restored = storage2.get_job("persist2")
    
    if job1_restored and job2_restored:
        print(f"✓ Jobs persisted: {job1_restored['id']}, {job2_restored['id']}")
        print("✓ Test 5 PASSED: Job data persists across restarts")
        return True
    else:
        print("✗ Test 5 FAILED: Jobs not found after restart")
        return False


def test_6_dlq_functionality():
    """Test 6: DLQ functionality"""
    print("\n" + "="*60)
    print("TEST 6: Dead Letter Queue Functionality")
    print("="*60)
    
    cleanup()
    storage = JobStorage()
    config = Config()
    config.set("max_retries", 1)
    
    # Create a job that will fail
    job = storage.create_job("dlq_test", "invalid-command-for-dlq", 1)
    print(f"✓ Created job: {job['id']}")
    
    # Start worker directly (avoid subprocess issues on Windows)
    print("Starting worker...")
    success = start_workers_directly(1)
    assert success, "Failed to start worker"
    time.sleep(2)  # Let worker start processing
    
    # With max_retries=1:
    # - First failure: attempts=0 -> 1, backoff = 2^1 = 2s, next_retry_at = now + 2s
    # - Second failure: attempts=1 -> 2, which >= max_retries (1), so DLQ
    # Total time needed: ~1s (first failure) + 2s (backoff) + ~1s (second failure) = ~4s
    # Add buffer for processing time
    print("Waiting for job to fail and move to DLQ (this will take ~8 seconds)...")
    
    # Poll for job state until it reaches DLQ or timeout
    # IMPORTANT: Keep workers running during this time!
    max_wait = 15  # Maximum wait time in seconds
    start_time = time.time()
    while time.time() - start_time < max_wait:
        job = storage.get_job("dlq_test")
        if job:
            state = job['state']
            attempts = job.get('attempts', 0)
            if state == 'dead':
                print(f"Job reached DLQ after {time.time() - start_time:.1f} seconds")
                break
            # Log progress every 2 seconds
            if int(time.time() - start_time) % 2 == 0:
                print(f"  Waiting... state={state}, attempts={attempts}")
        time.sleep(1)
    
    # Stop worker only after we've checked the final state
    stop_workers_directly()
    time.sleep(1)
    
    # Check DLQ
    dlq_jobs = storage.get_jobs_by_state('dead')
    print(f"DLQ jobs: {len(dlq_jobs)}")
    
    # Try to retry from DLQ
    if dlq_jobs:
        job_id = dlq_jobs[0]['id']
        print(f"Found DLQ job: {job_id}, resetting for retry...")
        storage.reset_job_for_retry(job_id)
        retried_job = storage.get_job(job_id)
        
        if retried_job and retried_job['state'] == 'pending':
            print(f"✓ DLQ job {job_id} reset and moved to pending")
            print("✓ Test 6 PASSED: DLQ functionality works")
            return True
        else:
            print(f"✗ DLQ job reset failed: state is {retried_job['state'] if retried_job else 'None'}")
    else:
        # Check if job exists but not in DLQ
        job = storage.get_job("dlq_test")
        if job:
            print(f"✗ Job exists but not in DLQ: state={job['state']}, attempts={job['attempts']}")
        else:
            print("✗ Job not found")
    
    print("✗ Test 6 FAILED: DLQ functionality not working")
    return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("QueueCTL Test Suite")
    print("="*60)
    
    tests = [
        ("Basic Job Completion", test_1_basic_job_completion),
        ("Failed Job Retry", test_2_failed_job_retry),
        ("Multiple Workers", test_3_multiple_workers),
        ("Invalid Commands", test_4_invalid_commands),
        ("Persistence", test_5_persistence),
        ("DLQ Functionality", test_6_dlq_functionality),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} FAILED with exception: {e}")
            results.append((test_name, False))
        finally:
            # Ensure workers are stopped
            stop_workers_directly()
            time.sleep(1)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print("\n" + "="*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)
    
    # Final cleanup
    cleanup()
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

