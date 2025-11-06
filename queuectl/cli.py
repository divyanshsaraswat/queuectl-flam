"""CLI interface for QueueCTL"""

import click
import json
import sys
import os
import multiprocessing
import signal
import time
from typing import Optional
from .storage import JobStorage
from .config import Config
from .worker import Worker


# Global storage and config instances
storage = None
config = None
worker_processes = []


def get_storage():
    """Get or create storage instance"""
    global storage
    if storage is None:
        storage = JobStorage()
    return storage


def get_config():
    """Get or create config instance"""
    global config
    if config is None:
        config = Config()
    return config


def generate_job_id() -> str:
    """Generate a unique job ID"""
    import uuid
    return f"job_{uuid.uuid4().hex[:8]}"


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """QueueCTL - A CLI-based background job queue system"""
    pass


@cli.command()
@click.argument('job_data', required=False)
def enqueue(job_data: Optional[str]):
    """Enqueue a new job to the queue
    
    JOB_DATA: JSON string with job details (id, command, max_retries)
    
    Example: queuectl enqueue '{"id":"job1","command":"sleep 2","max_retries":3}'
    """
    storage = get_storage()
    cfg = get_config()
    
    if job_data:
        try:
            job_dict = json.loads(job_data)
            job_id = job_dict.get('id') or generate_job_id()
            command = job_dict.get('command')
            max_retries = job_dict.get('max_retries', cfg.get('max_retries', 3))
            
            if not command:
                click.echo("Error: 'command' field is required", err=True)
                sys.exit(1)
            
        except json.JSONDecodeError:
            click.echo("Error: Invalid JSON format", err=True)
            sys.exit(1)
    else:
        # Interactive mode
        job_id = click.prompt("Job ID", default=generate_job_id())
        command = click.prompt("Command")
        max_retries = click.prompt("Max retries", default=cfg.get('max_retries', 3), type=int)
    
    job = storage.create_job(job_id, command, max_retries)
    click.echo(f"Job enqueued: {job_id}")
    click.echo(json.dumps(job, indent=2))


@cli.group()
def worker():
    """Manage worker processes"""
    pass


@worker.command()
@click.option('--count', default=1, help='Number of worker processes to start')
def start(count: int):
    """Start one or more worker processes"""
    storage = get_storage()
    cfg = get_config()
    
    # Check if workers are already running
    pid_file = "queuectl.workers.pid"
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
            click.echo(f"Warning: {len(alive_pids)} worker(s) already running (PIDs: {alive_pids})")
            click.echo("Use 'queuectl worker stop' to stop them first")
            return
    
    # Start workers
    processes = []
    for i in range(count):
        def worker_func(worker_id):
            worker = Worker(worker_id, storage, cfg)
            worker.run()
        
        p = multiprocessing.Process(target=worker_func, args=(i + 1,))
        p.start()
        processes.append(p)
        click.echo(f"Started worker {i + 1} (PID: {p.pid})")
    
    # Save PIDs
    with open(pid_file, 'w') as f:
        f.write('\n'.join(str(p.pid) for p in processes))
    
    click.echo(f"\nStarted {count} worker(s). Use 'queuectl worker stop' to stop them.")


@worker.command()
def stop():
    """Stop all running worker processes gracefully"""
    pid_file = "queuectl.workers.pid"
    
    if not os.path.exists(pid_file):
        click.echo("No workers running")
        return
    
    with open(pid_file, 'r') as f:
        pids = [int(pid) for pid in f.read().strip().split('\n') if pid]
    
    if not pids:
        click.echo("No workers running")
        return
    
    # Send SIGTERM to all workers
    stopped = 0
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped += 1
            click.echo(f"Sent stop signal to worker (PID: {pid})")
        except OSError as e:
            click.echo(f"Worker (PID: {pid}) not found: {e}")
    
    # Wait a bit for graceful shutdown
    time.sleep(2)
    
    # Force kill if still running
    for pid in pids:
        try:
            os.kill(pid, 0)  # Check if alive
            os.kill(pid, signal.SIGKILL)
            click.echo(f"Force killed worker (PID: {pid})")
        except OSError:
            pass
    
    # Remove PID file
    os.remove(pid_file)
    click.echo(f"Stopped {stopped} worker(s)")


@cli.command()
def status():
    """Show summary of all job states and active workers"""
    storage = get_storage()
    
    stats = storage.get_stats()
    
    click.echo("\n=== Queue Status ===")
    click.echo(f"Total Jobs: {stats['total']}")
    click.echo(f"Pending: {stats['pending']}")
    click.echo(f"Processing: {stats['processing']}")
    click.echo(f"Completed: {stats['completed']}")
    click.echo(f"Failed: {stats['failed']}")
    click.echo(f"Dead (DLQ): {stats['dead']}")
    
    # Check active workers
    pid_file = "queuectl.workers.pid"
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            pids = [int(pid) for pid in f.read().strip().split('\n') if pid]
        
        alive_workers = 0
        for pid in pids:
            try:
                os.kill(pid, 0)
                alive_workers += 1
            except OSError:
                pass
        
        click.echo(f"\nActive Workers: {alive_workers}")
    else:
        click.echo("\nActive Workers: 0")


@cli.command()
@click.option('--state', type=click.Choice(['pending', 'processing', 'completed', 'failed', 'dead']), 
              default=None, help='Filter by job state')
def list(state: Optional[str]):
    """List jobs, optionally filtered by state"""
    storage = get_storage()
    
    if state:
        jobs = storage.get_jobs_by_state(state)
        click.echo(f"\n=== Jobs ({state}) ===")
    else:
        # Show all jobs grouped by state
        click.echo("\n=== All Jobs ===")
        for state_name in ['pending', 'processing', 'completed', 'failed', 'dead']:
            jobs = storage.get_jobs_by_state(state_name)
            if jobs:
                click.echo(f"\n{state_name.upper()}:")
                for job in jobs:
                    click.echo(f"  {job['id']}: {job['command']} (attempts: {job['attempts']}/{job['max_retries']})")
        return
    
    if not jobs:
        click.echo("No jobs found")
        return
    
    for job in jobs:
        output = {
            "id": job['id'],
            "command": job['command'],
            "state": job['state'],
            "attempts": job['attempts'],
            "max_retries": job['max_retries'],
            "created_at": job['created_at'],
            "updated_at": job['updated_at']
        }
        if job.get('error_message'):
            output['error_message'] = job['error_message']
        click.echo(json.dumps(output, indent=2))


@cli.group()
def dlq():
    """Manage Dead Letter Queue"""
    pass


@dlq.command()
def list():
    """List all jobs in the Dead Letter Queue"""
    storage = get_storage()
    jobs = storage.get_jobs_by_state('dead')
    
    if not jobs:
        click.echo("Dead Letter Queue is empty")
        return
    
    click.echo("\n=== Dead Letter Queue ===")
    for job in jobs:
        click.echo(f"\nJob ID: {job['id']}")
        click.echo(f"Command: {job['command']}")
        click.echo(f"Attempts: {job['attempts']}/{job['max_retries']}")
        click.echo(f"Error: {job.get('error_message', 'Unknown error')}")
        click.echo(f"Created: {job['created_at']}")


@dlq.command()
@click.argument('job_id')
def retry(job_id: str):
    """Retry a job from the Dead Letter Queue"""
    storage = get_storage()
    
    job = storage.get_job(job_id)
    if not job:
        click.echo(f"Error: Job '{job_id}' not found", err=True)
        sys.exit(1)
    
    if job['state'] != 'dead':
        click.echo(f"Error: Job '{job_id}' is not in DLQ (state: {job['state']})", err=True)
        sys.exit(1)
    
    storage.reset_job_for_retry(job_id)
    click.echo(f"Job '{job_id}' reset and moved back to pending queue")


@cli.group()
def config():
    """Manage configuration"""
    pass


@config.command()
@click.argument('key')
@click.argument('value')
def set(key: str, value: str):
    """Set a configuration value
    
    Example: queuectl config set max-retries 5
    """
    cfg = get_config()
    
    # Convert value to appropriate type
    if value.isdigit():
        value = int(value)
    elif value.replace('.', '', 1).isdigit():
        value = float(value)
    elif value.lower() in ('true', 'false'):
        value = value.lower() == 'true'
    
    cfg.set(key, value)
    click.echo(f"Set {key} = {value}")


@config.command()
@click.argument('key', required=False)
def get(key: Optional[str]):
    """Get configuration value(s)"""
    cfg = get_config()
    
    if key:
        value = cfg.get(key)
        click.echo(f"{key} = {value}")
    else:
        click.echo("\n=== Configuration ===")
        all_config = cfg.get_all()
        for k, v in all_config.items():
            click.echo(f"{k} = {v}")


if __name__ == '__main__':
    cli()

