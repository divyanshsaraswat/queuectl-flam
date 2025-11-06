# QueueCTL - Background Job Queue System

A CLI-based background job queue system with worker processes, automatic retries with exponential backoff, and Dead Letter Queue (DLQ) support.

## 🚀 Features

- **Job Management**: Enqueue, monitor, and manage background jobs
- **Worker Processes**: Run multiple worker processes in parallel
- **Automatic Retries**: Exponential backoff retry mechanism for failed jobs
- **Dead Letter Queue**: Permanent storage for jobs that exhaust retries
- **Persistent Storage**: SQLite-based persistence across restarts
- **Concurrency Safety**: Locking mechanism prevents duplicate job processing
- **Graceful Shutdown**: Workers finish current jobs before stopping
- **Configuration Management**: Adjustable retry count and backoff settings

## 📋 Requirements

- Python 3.8 or higher
- pip (Python package manager)

## 🛠️ Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd flam-submission
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Make CLI Executable (Optional)

On Unix/Linux/Mac:
```bash
chmod +x queuectl.py
```

On Windows, you can use:
```bash
python queuectl.py <command>
```

Or install as a package:
```bash
pip install -e .
```

## 💻 Usage Examples

### Basic Commands

#### Enqueue a Job

```bash
# Enqueue with JSON data
python queuectl.py enqueue '{"id":"job1","command":"echo Hello World","max_retries":3}'

# Interactive mode (if no JSON provided)
python queuectl.py enqueue
```

#### Start Workers

```bash
# Start a single worker
python queuectl.py worker start

# Start multiple workers
python queuectl.py worker start --count 3
```

#### Check Status

```bash
python queuectl.py status
```

Output:
```
=== Queue Status ===
Total Jobs: 10
Pending: 2
Processing: 1
Completed: 5
Failed: 1
Dead (DLQ): 1

Active Workers: 3
```

#### List Jobs

```bash
# List all jobs
python queuectl.py list

# List jobs by state
python queuectl.py list --state pending
python queuectl.py list --state completed
python queuectl.py list --state dead
```

#### Stop Workers

```bash
python queuectl.py worker stop
```

### Dead Letter Queue (DLQ)

#### List DLQ Jobs

```bash
python queuectl.py dlq list
```

#### Retry a DLQ Job

```bash
python queuectl.py dlq retry job1
```

### Configuration

#### Set Configuration

```bash
# Set max retries
python queuectl.py config set max-retries 5

# Set backoff base (for exponential backoff: delay = base^attempts)
python queuectl.py config set backoff_base 3
```

#### Get Configuration

```bash
# Get all configuration
python queuectl.py config get

# Get specific value
python queuectl.py config get max-retries
```

### Complete Workflow Example

```bash
# 1. Start workers
python queuectl.py worker start --count 2

# 2. Enqueue some jobs
python queuectl.py enqueue '{"id":"job1","command":"echo Success","max_retries":3}'
python queuectl.py enqueue '{"id":"job2","command":"sleep 2","max_retries":3}'
python queuectl.py enqueue '{"id":"job3","command":"invalid-command-that-fails","max_retries":2}'

# 3. Check status
python queuectl.py status

# 4. List pending jobs
python queuectl.py list --state pending

# 5. Wait for processing (jobs will be processed automatically)
# Check status again after a few seconds
python queuectl.py status

# 6. Check DLQ if any jobs failed
python queuectl.py dlq list

# 7. Stop workers when done
python queuectl.py worker stop
```

## 🏗️ Architecture Overview

### Job Lifecycle

```
pending → processing → completed
                    ↓
                  failed → (retry with backoff) → pending
                                   ↓
                                dead (DLQ)
```

### Components

1. **Storage Module** (`queuectl/storage.py`)
   - SQLite database for persistent job storage
   - File-based locking for concurrency control
   - Job state management and atomic operations

2. **Worker Module** (`queuectl/worker.py`)
   - Worker processes that execute jobs
   - Command execution with timeout handling
   - Retry logic with exponential backoff
   - Graceful shutdown support

3. **Configuration Module** (`queuectl/config.py`)
   - JSON-based configuration storage
   - Thread-safe configuration access
   - Default values and validation

4. **CLI Module** (`queuectl/cli.py`)
   - Command-line interface using Click
   - All user-facing commands
   - Worker process management

### Data Persistence

- **Database**: SQLite (`queuectl.db`)
- **Configuration**: JSON file (`queuectl.config.json`)
- **Worker PIDs**: Text file (`queuectl.workers.pid`)
- **Locks**: File-based locks for concurrent access

### Retry Mechanism

Failed jobs are retried with exponential backoff:
- **Formula**: `delay = base ^ attempts` seconds
- **Default base**: 2
- After max retries, jobs move to DLQ

Example:
- Attempt 1 fails → retry in 2^1 = 2 seconds
- Attempt 2 fails → retry in 2^2 = 4 seconds
- Attempt 3 fails → retry in 2^3 = 8 seconds
- Attempt 4 fails → move to DLQ (if max_retries = 3)

### Concurrency Safety

- **File locking**: Prevents race conditions in database operations
- **Atomic job claiming**: Only one worker can claim a pending job
- **Process isolation**: Each worker runs in a separate process

## 🧪 Testing Instructions

Run the test script to validate core functionality:

```bash
python test_queuectl.py
```

The test script validates:
1. ✅ Basic job completion
2. ✅ Failed job retries with backoff
3. ✅ Multiple workers processing jobs without overlap
4. ✅ Invalid commands failing gracefully
5. ✅ Job data persistence across restarts
6. ✅ DLQ functionality

### Manual Testing Scenarios

1. **Basic Job Success**
   ```bash
   python queuectl.py enqueue '{"id":"test1","command":"echo test","max_retries":3}'
   python queuectl.py worker start
   # Wait a few seconds, then check status
   python queuectl.py list --state completed
   ```

2. **Failed Job with Retries**
   ```bash
   python queuectl.py enqueue '{"id":"test2","command":"nonexistent-command","max_retries":3}'
   # Watch workers retry with increasing delays
   python queuectl.py status
   ```

3. **Multiple Workers**
   ```bash
   python queuectl.py worker start --count 3
   # Enqueue multiple jobs
   for i in {1..5}; do
     python queuectl.py enqueue "{\"id\":\"job$i\",\"command\":\"sleep 1\"}"
   done
   # Watch all workers process jobs in parallel
   ```

4. **Persistence Test**
   ```bash
   # Enqueue jobs
   python queuectl.py enqueue '{"id":"persist1","command":"echo test"}'
   # Stop workers
   python queuectl.py worker stop
   # Restart workers
   python queuectl.py worker start
   # Jobs should still be there
   python queuectl.py list
   ```

## 📊 Assumptions & Trade-offs

### Assumptions

1. **Command Execution**: Commands are executed as shell commands (bash on Unix, cmd on Windows)
2. **Exit Codes**: Success = exit code 0, failure = non-zero exit code
3. **Timeout**: Jobs have a 5-minute execution timeout
4. **Storage**: SQLite is sufficient for job persistence (not optimized for high-throughput)
5. **Worker Management**: Workers are managed via PID files (simple approach)

### Trade-offs

1. **File-based Locking**: Uses file locks instead of database-level locking for simplicity
2. **Polling**: Workers poll for jobs every 0.5 seconds (could use database notifications)
3. **No Priority Queues**: Jobs are processed FIFO (first-in, first-out)
4. **No Job Scheduling**: No support for delayed/scheduled jobs (bonus feature)
5. **No Output Logging**: Command output is not stored (bonus feature)

### Design Decisions

1. **SQLite over JSON files**: Better for concurrent access and querying
2. **Multiprocessing over Threading**: True parallelism for workers
3. **Click CLI framework**: Clean, maintainable CLI interface
4. **File-based config**: Simple, no external dependencies

## 🚧 Known Limitations

- No job priority support
- No scheduled/delayed jobs
- No job output logging
- No web dashboard
- Workers must be stopped manually (no auto-restart)
- Limited to single-machine deployment

## 📝 File Structure

```
flam-submission/
├── queuectl/
│   ├── __init__.py          # Package initialization
│   ├── storage.py           # Job persistence and database operations
│   ├── worker.py            # Worker process implementation
│   ├── config.py            # Configuration management
│   └── cli.py               # CLI interface
├── queuectl.py              # Entry point script
├── requirements.txt         # Python dependencies
├── test_queuectl.py        # Test script
├── README.md               # This file
├── queuectl.db             # SQLite database (created at runtime)
├── queuectl.config.json    # Configuration file (created at runtime)
└── queuectl.workers.pid    # Worker PID file (created at runtime)
```

## 🔧 Troubleshooting

### Workers Not Starting

- Check if workers are already running: `python queuectl.py status`
- Stop existing workers: `python queuectl.py worker stop`
- Check for permission issues on PID file

### Jobs Not Processing

- Verify workers are running: `python queuectl.py status`
- Check job state: `python queuectl.py list --state pending`
- Ensure database file is writable

### Database Locked Errors

- Stop all workers: `python queuectl.py worker stop`
- Delete lock file: `rm queuectl.db.lock` (Unix) or delete manually (Windows)
- Restart workers

## 📄 License

This project is part of a technical assessment.

## 👤 Author

Created as part of QueueCTL Backend Developer Internship Assignment.

---

## ✅ Checklist

- [x] Working CLI application (`queuectl`)
- [x] Persistent job storage (SQLite)
- [x] Multiple worker support
- [x] Retry mechanism with exponential backoff
- [x] Dead Letter Queue
- [x] Configuration management
- [x] Clean CLI interface with help texts
- [x] Comprehensive README.md
- [x] Code structured with clear separation of concerns
- [x] Test script to validate core flows

## 📹 Demo

A working CLI demo has been recorded and can be accessed via the provided link in the repository (if applicable).

