import asyncio
import json
from typing import List, Dict, Any
import time

async def run_workflow_batch(workflows: List[Dict], registry, mode: str = 'sequential'):
    """
    Execute multiple workflows in batch mode.
    
    Args:
        workflows: List of workflow definitions
        registry: MCP client registry
        mode: 'sequential' or 'parallel'
    
    Returns:
        List of execution results with comparison data
    """
    if mode == 'sequential':
        return await _run_sequential(workflows, registry)
    elif mode == 'parallel':
        return await _run_parallel(workflows, registry)
    else:
        raise ValueError(f"Invalid batch mode: {mode}")

async def _run_sequential(workflows: List[Dict], registry) -> List[Dict]:
    """Run workflows one after another."""
    from backend.workflow import run_workflow
    
    results = []
    start_time = time.time()
    
    for idx, workflow in enumerate(workflows):
        workflow_start = time.time()
        try:
            result = await run_workflow(workflow, registry)
            duration_ms = (time.time() - workflow_start) * 1000
            
            results.append({
                'workflowId': workflow.get('id', f'workflow-{idx}'),
                'workflowName': workflow.get('name', f'Workflow {idx + 1}'),
                'status': 'completed' if not result.get('error') else 'failed',
                'statusMessage': result.get('error', 'Completed successfully'),
                'durationMs': duration_ms,
                'timestamp': time.time() * 1000,
                'output': result.get('output'),
                'logs': result.get('logs', []),
                'stats': result.get('stats', {}),
                'retrievals': result.get('retrievals', []),
                'nodeResults': result.get('nodeResults', {}),
            })
        except Exception as exc:
            duration_ms = (time.time() - workflow_start) * 1000
            results.append({
                'workflowId': workflow.get('id', f'workflow-{idx}'),
                'workflowName': workflow.get('name', f'Workflow {idx + 1}'),
                'status': 'failed',
                'statusMessage': str(exc),
                'durationMs': duration_ms,
                'timestamp': time.time() * 1000,
                'error': str(exc),
            })
    
    total_duration = (time.time() - start_time) * 1000
    return {
        'mode': 'sequential',
        'totalDurationMs': total_duration,
        'workflowCount': len(workflows),
        'reports': results,
    }

async def _run_parallel(workflows: List[Dict], registry) -> List[Dict]:
    """Run workflows simultaneously."""
    from backend.workflow import run_workflow
    
    async def run_single(workflow, idx):
        workflow_start = time.time()
        try:
            result = await run_workflow(workflow, registry)
            duration_ms = (time.time() - workflow_start) * 1000
            
            return {
                'workflowId': workflow.get('id', f'workflow-{idx}'),
                'workflowName': workflow.get('name', f'Workflow {idx + 1}'),
                'status': 'completed' if not result.get('error') else 'failed',
                'statusMessage': result.get('error', 'Completed successfully'),
                'durationMs': duration_ms,
                'timestamp': time.time() * 1000,
                'output': result.get('output'),
                'logs': result.get('logs', []),
                'stats': result.get('stats', {}),
                'retrievals': result.get('retrievals', []),
                'nodeResults': result.get('nodeResults', {}),
            }
        except Exception as exc:
            duration_ms = (time.time() - workflow_start) * 1000
            return {
                'workflowId': workflow.get('id', f'workflow-{idx}'),
                'workflowName': workflow.get('name', f'Workflow {idx + 1}'),
                'status': 'failed',
                'statusMessage': str(exc),
                'durationMs': duration_ms,
                'timestamp': time.time() * 1000,
                'error': str(exc),
            }
    
    start_time = time.time()
    tasks = [run_single(workflow, idx) for idx, workflow in enumerate(workflows)]
    results = await asyncio.gather(*tasks)
    total_duration = (time.time() - start_time) * 1000
    
    return {
        'mode': 'parallel',
        'totalDurationMs': total_duration,
        'workflowCount': len(workflows),
        'reports': results,
    }

def generate_comparison_summary(batch_result: Dict) -> Dict[str, Any]:
    """Generate summary statistics for batch execution."""
    reports = batch_result.get('reports', [])
    if not reports:
        return {}
    
    durations = [r.get('durationMs', 0) for r in reports]
    statuses = [r.get('status') for r in reports]
    
    return {
        'totalWorkflows': len(reports),
        'successCount': sum(1 for s in statuses if s == 'completed'),
        'failureCount': sum(1 for s in statuses if s == 'failed'),
        'minDuration': min(durations) if durations else 0,
        'maxDuration': max(durations) if durations else 0,
        'avgDuration': sum(durations) / len(durations) if durations else 0,
        'totalDuration': batch_result.get('totalDurationMs', 0),
        'mode': batch_result.get('mode'),
        'timeSpeedupFactor': calculate_speedup(batch_result),
    }

def calculate_speedup(batch_result: Dict) -> float:
    """Calculate speedup factor for parallel vs sequential execution."""
    reports = batch_result.get('reports', [])
    if not reports or batch_result.get('mode') != 'parallel':
        return 1.0
    
    sum_individual_times = sum(r.get('durationMs', 0) for r in reports)
    parallel_time = batch_result.get('totalDurationMs', 1)
    
    return sum_individual_times / parallel_time if parallel_time > 0 else 1.0
