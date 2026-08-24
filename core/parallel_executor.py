# apa/core/parallel_executor.py
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Callable

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class ParallelExecutor:
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers

    def run(self, tasks: List[dict], runner_func: Callable) -> Dict[str, Any]:
        task_count = len(tasks)
        logger.info(f"Iniciando pool de ejecución paralela con {task_count} tareas")

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        success = True

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task_id = {}
            for i, task in enumerate(tasks):
                task_id = task.get("id", task.get("task_id", str(i)))
                future = executor.submit(runner_func, task)
                future_to_task_id[future] = task_id

            for future in as_completed(future_to_task_id):
                task_id = future_to_task_id[future]
                try:
                    results[task_id] = future.result()
                except Exception as exc:
                    errors[task_id] = str(exc)
                    success = False

        logger.info(f"Finalizado pool de ejecución paralela con {task_count} tareas")
        return {
            "success": success,
            "results": results,
            "errors": errors
        }


if __name__ == "__main__":
    def _mock_runner(task: dict) -> dict:
        delay = task.get("delay", 0.2)
        time.sleep(delay)
        if task.get("should_fail", False):
            raise RuntimeError(f"Fallo simulado en {task.get('id')}")
        return {"output": f"Completado {task.get('id')}", "delay": delay}

    batch_tasks = [
        {"id": "t1", "delay": 1.0},
        {"id": "t2", "delay": 1.0},
        {"id": "t3", "delay": 1.0},
        {"id": "t_fail", "delay": 0.3, "should_fail": True}
    ]

    executor = ParallelExecutor(max_workers=3)
    start_ts = time.time()
    res = executor.run(batch_tasks, _mock_runner)
    elapsed = time.time() - start_ts

    assert res["success"] is False
    assert len(res["results"]) == 3
    assert len(res["errors"]) == 1
    assert "t_fail" in res["errors"]
    assert elapsed < 2.5, f"Tiempo paralelo ({elapsed:.2f}s) no refleja concurrencia esperada"

    print("✅ T5 - ParallelExecutor: Todas las pruebas pasaron.")