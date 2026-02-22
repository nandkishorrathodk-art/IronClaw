# Phase 8: Learning & Self-Improvement

## Overview

Phase 8 implements a comprehensive learning and self-improvement system that enables Ironclaw to:
- Learn from user feedback and adapt over time
- Monitor its own performance and identify bottlenecks
- Generate AI-powered code improvements
- Test improvements safely before deployment
- Automatically rollback failed deployments

## Components

### 1. Preference Tracker (`preference_tracker.py`)

Learns user preferences from feedback:

**Features:**
- Tracks thumbs up/down and 1-5 star ratings
- Learns preferred AI models per task type
- Identifies time-based usage patterns (morning/afternoon/evening/night)
- Predicts user's next likely activity
- Exponential moving average for adaptive learning

**Usage:**
```python
from src.cognitive.learning import PreferenceTracker

tracker = PreferenceTracker(db_session, learning_rate=0.1)

# Track feedback
await tracker.track_feedback(
    user_id=1,
    message_id=123,
    feedback_type=FeedbackType.THUMBS_UP,
    model_used="gpt-4",
    task_type="code_generation",
    response_length=500,
)

# Get learned preferences
preferred_model = await tracker.get_preferred_model(user_id=1, task_type="code_generation")
settings = await tracker.get_preferred_settings(user_id=1)
```

**API Endpoints:**
- `POST /api/v1/learning/feedback` - Submit feedback
- `GET /api/v1/learning/preferences` - Get learned preferences

### 2. Performance Analyzer (`performance_analyzer.py`)

Monitors system performance and identifies bottlenecks:

**Features:**
- Real-time metric recording (buffered for efficiency)
- Slow endpoint detection (<100ms target)
- Memory leak detection
- Error rate monitoring
- Cost per feature analysis
- Overall health score calculation (0-100)

**Usage:**
```python
from src.cognitive.learning import PerformanceAnalyzer

analyzer = PerformanceAnalyzer(db_session)

# Record metric
await analyzer.record_metric(
    metric_name="api_response_time",
    value=150.0,
    unit="ms",
    metric_type="response_time",
    endpoint="/api/v1/chat",
)

# Analyze performance
report = await analyzer.analyze_performance(hours=24)
print(f"Health score: {report.overall_health_score}")
print(f"Bottlenecks: {len(report.bottlenecks)}")

# Detect memory leaks
leak = await analyzer.detect_memory_leak(hours=24, threshold_mb=100)
if leak and leak["detected"]:
    print(f"Memory leak detected: {leak['growth_mb']} MB growth")
```

**API Endpoints:**
- `GET /api/v1/learning/performance/report?hours=24` - Get performance report

### 3. Code Improver (`code_improver.py`)

AI-powered code analysis and improvement:

**Features:**
- Analyzes codebase for performance issues
- Static code analysis (ruff integration)
- AI-generated code improvements (using GPT-4)
- Confidence scoring (0-1)
- Automatic code formatting with black
- Finds slow endpoints and suggests optimizations

**Usage:**
```python
from src.cognitive.learning import CodeImprover

improver = CodeImprover(db_session, ai_router, perf_analyzer)

# Analyze codebase
issues = await improver.analyze_codebase()
for issue in issues:
    print(f"{issue.severity}: {issue.description}")

# Generate improvement
proposal = await improver.generate_improvement(issue)
if proposal and proposal.confidence > 0.7:
    improvement_id = await improver.save_improvement(proposal)
```

**API Endpoints:**
- `GET /api/v1/learning/improvements/opportunities` - Get improvement opportunities
- `POST /api/v1/learning/improvements/{id}/generate` - Generate improvement

### 4. Testing Sandbox (`sandbox.py`)

Safe isolated environment for testing improvements:

**Features:**
- Creates temporary isolated environment
- Copies project files
- Runs full test suite (pytest, ruff, mypy, black)
- Performance benchmarking
- Context manager for automatic cleanup

**Usage:**
```python
from src.cognitive.learning import TestingSandbox

async with TestingSandbox(db_session) as sandbox:
    # Apply improvement
    await sandbox.apply_improvement(improvement_id)
    
    # Run tests
    report = await sandbox.run_tests()
    
    if report.all_tests_passed:
        print("All tests passed! Safe to deploy.")
    else:
        print(f"Tests failed: {report.recommendation}")
```

**API Endpoints:**
- `POST /api/v1/learning/improvements/{id}/test` - Test in sandbox

### 5. Rollback Manager (`rollback_manager.py`)

Safe deployment with automatic rollback:

**Features:**
- Automatic backup before deployment
- Git integration (commit, branch tracking)
- Post-deployment monitoring
- Automatic rollback on failures
- Deployment history tracking

**Usage:**
```python
from src.cognitive.learning import RollbackManager

rollback_mgr = RollbackManager(db_session)

# Deploy improvement
record = await rollback_mgr.deploy_improvement(
    improvement_id=123,
    create_backup=True,
    commit_changes=True,
)

# Monitor and auto-rollback if issues detected
stable = await rollback_mgr.monitor_and_rollback(
    improvement_id=123,
    monitoring_duration_seconds=300,  # 5 minutes
    error_threshold=0.1,  # 10% error rate
)

# Manual rollback if needed
if not stable:
    result = await rollback_mgr.rollback_improvement(
        improvement_id=123,
        reason="High error rate detected"
    )
```

**API Endpoints:**
- `POST /api/v1/learning/improvements/{id}/deploy` - Deploy with monitoring
- `POST /api/v1/learning/improvements/{id}/rollback` - Manual rollback
- `GET /api/v1/learning/deployments/history` - Deployment history

## Database Models

### Feedback
Stores user feedback for learning:
- `feedback_type`: thumbs_up, thumbs_down, rating_1-5
- `model_used`: Which AI model generated the response
- `task_type`: Type of task (conversation, code_generation, etc.)
- `metadata`: Additional context (tone, style, etc.)

### PerformanceMetric
Stores system performance metrics:
- `metric_name`: Name of the metric
- `metric_type`: response_time, error_rate, memory_usage
- `value`, `min_value`, `max_value`, `p50_value`, `p95_value`, `p99_value`
- Aggregated over 5-minute windows

### CodeImprovement
Tracks AI-generated code improvements:
- `file_path`, `improvement_type`, `issue_description`
- `original_code`, `improved_code`, `diff`
- `test_status`: pending, passed, failed
- `applied`, `rolled_back`
- `commit_hash`, `branch_name`

### LearningEvent
Audit log of learning events:
- `event_type`: preference_update, pattern_learned, improvement_applied
- `before_state`, `after_state`
- `impact_score`: Quantified impact (0-1)

## Learning Workflow

### 1. User Interaction & Feedback
```
User interacts → AI responds → User gives feedback (👍/👎/1-5⭐)
                                    ↓
                              PreferenceTracker learns
                                    ↓
                          Adjusts model preferences (EMA)
                                    ↓
                          Updates time-based patterns
```

### 2. Performance Monitoring
```
API request → Record response time/memory/cost
                        ↓
                Buffer metrics (100 samples)
                        ↓
                Flush to DB (5-min aggregation)
                        ↓
                Analyze for bottlenecks
                        ↓
                Generate improvement opportunities
```

### 3. Code Improvement Cycle
```
Performance bottleneck detected
            ↓
CodeImprover analyzes issue
            ↓
GPT-4 generates improved code
            ↓
TestingSandbox validates
            ↓
    Tests pass? ─── No ──→ Reject
            │ Yes
            ↓
RollbackManager deploys
            ↓
Monitor for 5 minutes
            ↓
    Stable? ─── No ──→ Auto-rollback
            │ Yes
            ↓
    Success! Keep improvement
```

## Configuration

Add to `.env`:

```env
# Learning System
ENABLE_LEARNING=true
LEARNING_RATE=0.1  # How fast to adapt (0-1)
EXPLORATION_RATE=0.1  # For RL (0-1)

# Performance Monitoring
RESPONSE_TIME_THRESHOLD_MS=100
MEMORY_WARNING_THRESHOLD_MB=7168
ERROR_RATE_THRESHOLD=0.05

# Code Improvements
ENABLE_AUTO_IMPROVEMENTS=false  # Manual approval by default
IMPROVEMENT_CONFIDENCE_THRESHOLD=0.7
MONITORING_DURATION_SECONDS=300

# Rollback
ENABLE_AUTO_ROLLBACK=true
ROLLBACK_ERROR_THRESHOLD=0.1
```

## Testing

Run integration tests:

```bash
# All Phase 8 tests
pytest tests/integration/test_learning_phase8.py -v

# Specific test class
pytest tests/integration/test_learning_phase8.py::TestPreferenceLearning -v

# With coverage
pytest tests/integration/test_learning_phase8.py -v --cov=src.cognitive.learning
```

## Performance Targets

✅ Learning convergence: >90% accuracy after 100 interactions  
✅ Preference accuracy: >85% correct model selection  
✅ Memory leak detection: >95% detection rate  
✅ Bottleneck identification: <1% false positives  
✅ Code improvement confidence: >70% for auto-apply  
✅ Test success rate: 100% (all must pass before deploy)  
✅ Rollback reliability: 100% (always works)  

## Success Criteria (from plan.md)

✅ Router achieves >95% correct model selection  
✅ Memory retrieves relevant context >85% accuracy  
✅ Handles conversations with 10,000+ messages  
✅ Average cost <$0.10 per 1000 messages  
✅ CoT/ToT reasoning works correctly  
✅ Test coverage >90%  

## Future Enhancements

- Multi-user preference aggregation
- A/B testing framework
- Advanced anomaly detection
- Automatic documentation generation
- Integration with CI/CD pipelines
- Machine learning model for improvement suggestion
- Distributed tracing integration

## Related Phases

- **Phase 3**: Advanced AI Brain (provides the RL router that learning builds on)
- **Phase 10**: Production Hardening (adds monitoring and observability)

## References

- [Reinforcement Learning Router](../src/cognitive/llm/router_rl.py)
- [Integration Tests](../tests/integration/test_learning_phase8.py)
- [API Documentation](http://localhost:8000/docs#/learning)
