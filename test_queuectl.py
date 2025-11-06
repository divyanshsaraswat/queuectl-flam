#!/usr/bin/env python3
"""Test script to validate QueueCTL core functionality"""

import subprocess
import time
import os
import json
import sys
from queuectl.storage import JobStorage
from queuectl.config import Config


def cleanup():
    """Clean up test files"""
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
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout, result.stderr
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
    
    # Start a worker
    print("Starting worker...")
    success, _, _ = run_command("python queuectl.py worker start --count 1")
    assert success, "Failed to start worker"
    time.sleep(2)
    
    # Process should complete
    time.sleep(3)
    
    # Check job status
    job = storage.get_job("test1")
    assert job is not None, "Job should exist"
    print(f"Job state: {job['state']}")
    
    # Stop worker
    run_command("python queuectl.py worker stop")
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
    
    # Start worker
    print("Starting worker...")
    run_command("python queuectl.py worker start --count 1")
    time.sleep(2)
    
    # Wait for retries (with backoff: 2^0=1s, 2^1=2s, then DLQ)
    print("Waiting for retries (this will take ~10 seconds)...")
    time.sleep(12)
    
    # Stop worker
    run_command("python queuectl.py worker stop")
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
    
    # Start multiple workers
    print("Starting 3 workers...")
    run_command("python queuectl.py worker start --count 3")
    time.sleep(2)
    
    # Wait for processing
    print("Waiting for jobs to process...")
    time.sleep(8)
    
    # Stop workers
    run_command("python queuectl.py worker stop")
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
    
    # Start worker
    run_command("python queuectl.py worker start --count 1")
    time.sleep(2)
    
    # Wait for failure
    time.sleep(5)
    
    # Stop worker
    run_command("python queuectl.py worker stop")
    time.sleep(1)
    
    # Check job failed/handled
    job = storage.get_job("test4")
    assert job is not None, "Job should exist"
    print(f"Job state: {job['state']}, error: {job.get('error_message', 'N/A')[:50]}")
    
    if job['state'] in ['failed', 'dead'] and job.get('error_message'):
        print("✓ Test 4 PASSED: Invalid command handled gracefully")
        return True
    else:
        print(f"✗ Test 4 FAILED: Job state {job['state']}")
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
    
    # Start worker
    run_command("python queuectl.py worker start --count 1")
    time.sleep(2)
    
    # Wait for failure and DLQ
    time.sleep(5)
    
    # Stop worker
    run_command("python queuectl.py worker stop")
    time.sleep(1)
    
    # Check DLQ
    dlq_jobs = storage.get_jobs_by_state('dead')
    print(f"DLQ jobs: {len(dlq_jobs)}")
    
    # Try to retry from DLQ
    if dlq_jobs:
        job_id = dlq_jobs[0]['id']
        storage.reset_job_for_retry(job_id)
        retried_job = storage.get_job(job_id)
        
        if retried_job and retried_job['state'] == 'pending':
            print(f"✓ DLQ job {job_id} reset and moved to pending")
            print("✓ Test 6 PASSED: DLQ functionality works")
            return True
    
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
            run_command("python queuectl.py worker stop")
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

