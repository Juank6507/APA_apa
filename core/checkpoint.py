# apa/core/checkpoint.py
import os
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
import sys
from pathlib import Path

# Ajustar path para importaciones internas del proyecto APA
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import settings

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.setLevel(getattr(logging, getattr(settings, 'log_level', 'INFO').upper(), logging.INFO))
    logger.addHandler(handler)


class CheckpointManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.specs_dir = Path(__file__).parents[1] / "specs"
        self.project_dir = self.specs_dir / project_id
        self.checkpoint_path = self.project_dir / "plan.json"
        self.tmp_path = self.project_dir / "plan.json.tmp"
        self.backup_path = self.project_dir / "plan.json.bak"

    def save(self, plan: dict) -> bool:
        try:
            self.project_dir.mkdir(parents=True, exist_ok=True)
            
            current_version = 1
            if self.checkpoint_path.exists():
                try:
                    with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                        current_version = existing.get("checkpoint_version", 0) + 1
                except Exception:
                    pass
            
            plan["checkpoint_at"] = datetime.utcnow().isoformat()
            plan["checkpoint_version"] = current_version
            
            with open(self.tmp_path, 'w', encoding='utf-8') as f:
                json.dump(plan, f, indent=2, ensure_ascii=False)
            
            if self.checkpoint_path.exists():
                try:
                    shutil.copy2(self.checkpoint_path, self.backup_path)
                except Exception as e:
                    logger.warning(f"Failed to backup checkpoint: {e}")
            
            os.replace(str(self.tmp_path), str(self.checkpoint_path))
            
            n_tasks = len(plan.get("tasks", []))
            n_completed = sum(1 for t in plan.get("tasks", []) if t.get("status") == "completed")
            logger.info(f"Checkpoint saved: version={current_version} tasks={n_completed}/{n_tasks}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
            if self.tmp_path.exists():
                try:
                    self.tmp_path.unlink()
                except Exception:
                    pass
            return False

    def restore(self) -> dict | None:
        for path in [self.checkpoint_path, self.backup_path]:
            if path.exists():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if "project_id" not in data or "tasks" not in data:
                        continue
                    if data["project_id"] != self.project_id:
                        continue
                        
                    modified = False
                    for task in data.get("tasks", []):
                        if task.get("status") == "running":
                            task["status"] = "pending"
                            task["attempts"] = task.get("attempts", 0)
                            task["result"] = None
                            task["model_used"] = None
                            modified = True
                    
                    v = data.get("checkpoint_version", "?")
                    n_tasks = len(data.get("tasks", []))
                    n_completed = sum(1 for t in data.get("tasks", []) if t.get("status") == "completed")
                    logger.info(f"Checkpoint restored: version={v} tasks={n_completed}/{n_tasks}")
                    return data
                except json.JSONDecodeError:
                    logger.warning(f"Checkpoint corrupt at {path.name}, trying backup...")
                    continue
                except Exception as e:
                    logger.warning(f"Error reading checkpoint at {path.name}: {e}")
                    continue
        return None

    def exists(self) -> bool:
        if not self.checkpoint_path.exists():
            return False
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return "project_id" in data and "tasks" in data
        except Exception:
            return False

    def clear(self) -> bool:
        """
        Elimina todos los archivos de checkpoint del proyecto:
        - plan.json (checkpoint principal)
        - plan.json.bak (backup)
        """
        try:
            # A6: Eliminar tanto el checkpoint principal como el backup
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
            if self.backup_path.exists():
                self.backup_path.unlink()
            logger.info(f"Checkpoint cleared for project {self.project_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing checkpoint: {e}")
            return False

    def get_info(self) -> dict:
        info = {
            "exists": False,
            "project_id": None,
            "checkpoint_at": None,
            "checkpoint_version": None,
            "tasks_total": None,
            "tasks_completed": None,
            "tasks_pending": None,
            "tasks_failed": None,
            "recoverable": False
        }
        try:
            if not self.checkpoint_path.exists():
                return info
            
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "project_id" not in data or "tasks" not in data:
                return info
                
            info["exists"] = True
            info["project_id"] = data.get("project_id")
            info["checkpoint_at"] = data.get("checkpoint_at")
            info["checkpoint_version"] = data.get("checkpoint_version")
            
            tasks = data.get("tasks", [])
            info["tasks_total"] = len(tasks)
            info["tasks_completed"] = sum(1 for t in tasks if t.get("status") == "completed")
            info["tasks_pending"] = sum(1 for t in tasks if t.get("status") in ("pending", "running"))
            info["tasks_failed"] = sum(1 for t in tasks if t.get("status") == "failed")
            
            info["recoverable"] = info["tasks_pending"] > 0 or info["tasks_failed"] > 0
            
            return info
        except Exception:
            return info


if __name__ == "__main__":
    import shutil
    # PRUEBA 1 — ciclo completo save/restore
    try:
        cp = CheckpointManager("test-project-123")
        if cp.project_dir.exists():
            shutil.rmtree(cp.project_dir)
            
        plan = {
            "project_id": "test-project-123",
            "spec_summary": "test",
            "tasks": [
                {"id": "T1", "name": "task1", "status": "completed", "attempts": 1, "result": {"code": "x"}, "model_used": "m"},
                {"id": "T2", "name": "task2", "status": "running", "attempts": 1, "result": None, "model_used": None},
                {"id": "T3", "name": "task3", "status": "pending", "attempts": 0, "result": None, "model_used": None}
            ]
        }
        assert cp.save(plan) == True
        assert cp.exists() == True
        
        info = cp.get_info()
        assert info["tasks_total"] == 3
        assert info["tasks_completed"] == 1
        assert info["recoverable"] == True
        
        restored = cp.restore()
        assert restored is not None
        assert restored["project_id"] == "test-project-123"
        t2 = next(t for t in restored["tasks"] if t["id"] == "T2")
        assert t2["status"] == "pending"
        
        cp.save(plan)
        info2 = cp.get_info()
        assert info2["checkpoint_version"] == 2
        
        # A6: Verificar que clear() elimina ambos archivos
        assert cp.clear() == True
        assert not cp.checkpoint_path.exists(), "Checkpoint principal no eliminado"
        assert not cp.backup_path.exists(), "Backup no eliminado"
        print("PRUEBA 1 OK")
    except Exception as e:
        print(f"PRUEBA 1 FALLO: {e}")

    # PRUEBA 2 — simulación de crash
    try:
        cp2 = CheckpointManager("test-crash-456")
        if cp2.project_dir.exists():
            shutil.rmtree(cp2.project_dir)
        plan2 = {
            "project_id": "test-crash-456",
            "tasks": [
                {"id": "T1", "status": "running", "attempts": 1, "result": None, "model_used": None},
                {"id": "T2", "status": "running", "attempts": 1, "result": None, "model_used": None}
            ]
        }
        cp2.save(plan2)
        cp3 = CheckpointManager("test-crash-456")
        assert cp3.exists() == True
        restored2 = cp3.restore()
        for t in restored2["tasks"]:
            assert t["status"] != "running"
        print("PRUEBA 2 — simulación crash OK")
    except Exception as e:
        print(f"PRUEBA 2 FALLO: {e}")

    # PRUEBA 3 — checkpoint corrupto
    try:
        cp4 = CheckpointManager("test-corrupt-789")
        if cp4.project_dir.exists():
            shutil.rmtree(cp4.project_dir)
        cp4.project_dir.mkdir(parents=True, exist_ok=True)
        cp4.checkpoint_path.write_text("{ json corrupto {{{")
        result = cp4.restore()
        assert result is None
        assert cp4.exists() == False
        print("PRUEBA 3 — checkpoint corrupto OK")
    except Exception as e:
        print(f"PRUEBA 3 FALLO: {e}")

    # PRUEBA 4 — no existe checkpoint
    try:
        cp5 = CheckpointManager("proyecto-inexistente-999")
        if cp5.project_dir.exists():
            shutil.rmtree(cp5.project_dir)
        assert cp5.exists() == False
        assert cp5.restore() is None
        info = cp5.get_info()
        assert info["exists"] == False
        print("PRUEBA 4 — no existe OK")
    except Exception as e:
        print(f"PRUEBA 4 FALLO: {e}")

    print("=== CHECKPOINT OK — todas las pruebas pasaron ===")