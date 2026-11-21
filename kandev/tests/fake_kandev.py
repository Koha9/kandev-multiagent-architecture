"""内存里的 Kandev 替身：只实现 ma.py / build_workflows.py 部署路径用到的工具，供 test_ma.py 离线测试 apply 的门禁。
响应的形状照 build_workflows.py 对真实接口的用法写（import 时 move_to_step 的 step_position 换成 step_id 等）；
它验证的是 ma.py 的流程和门禁，不是 Kandev 的行为。"""
import copy
import itertools
import json

STATE = {"workflows": {}, "tasks": []}      # workflow id -> {"id", "workspace_id", "name", "description", "steps": [...]}
_ids = itertools.count(1)


def _wf(wid):
    return STATE["workflows"][wid]


class FakeKandev:
    def __init__(self, url=None, client="", version=""):
        self.url = url

    def call(self, name, args):
        if not hasattr(self, name):
            raise RuntimeError(f"{name} failed: 替身没有实现这个工具")
        return copy.deepcopy(getattr(self, name)(**args))

    def list_settings_resources_kandev(self, resource_type, workspace_id, limit=50):
        return {"resources": STATE.get("automations", [])}

    def list_workflows_kandev(self, workspace_id):
        return {"workflows": [{k: w[k] for k in ("id", "name", "description")} for w in STATE["workflows"].values()
                              if w["workspace_id"] == workspace_id]}

    def list_workflow_steps_kandev(self, workflow_id):
        return {"steps": _wf(workflow_id)["steps"]}

    def import_workflow_kandev(self, workspace_id, document):
        for wf in json.loads(document)["workflows"]:
            wid = f"wf-{next(_ids)}"
            steps = [{**s, "id": f"st-{next(_ids)}"} for s in wf["steps"]]
            id_at = {s["position"]: s["id"] for s in steps}
            for s in steps:
                s["events"] = {ev: [{"type": a["type"], "config": {"step_id": id_at[a["config"]["step_position"]]}}
                                    if a["type"] == "move_to_step" else a for a in acts] for ev, acts in s["events"].items()}
            STATE["workflows"][wid] = {"id": wid, "workspace_id": workspace_id, "name": wf["name"],
                                       "description": wf["description"], "steps": steps}
        return "ok"

    def update_workflow_kandev(self, workflow_id, **changes):
        _wf(workflow_id).update(changes)
        return "ok"

    def update_workflow_step_kandev(self, step_id, **changes):
        for w in STATE["workflows"].values():
            for s in w["steps"]:
                if s["id"] == step_id:
                    s.update(changes)
        return "ok"

    def reorder_workflow_steps_kandev(self, workflow_id, step_ids):
        by = {s["id"]: s for s in _wf(workflow_id)["steps"]}
        _wf(workflow_id)["steps"] = [{**by[i], "position": n} for n, i in enumerate(step_ids)]
        return "ok"

    def export_workflow_kandev(self, workflow_id):
        w = _wf(workflow_id)
        return {"type": "kandev_workflow", "version": 2,
                "workflows": [{"name": w["name"], "description": w["description"], "steps": w["steps"]}]}

    def list_tasks_kandev(self, workflow_id):
        return {"tasks": [t for t in STATE["tasks"] if t["workflow_id"] == workflow_id]}


def install():
    """把替身装进已导入的模块。在 `import ma` 之后调用。"""
    import build_workflows
    import kandev_client
    import ma
    for mod in (kandev_client, build_workflows, ma):
        mod.Kandev = FakeKandev
