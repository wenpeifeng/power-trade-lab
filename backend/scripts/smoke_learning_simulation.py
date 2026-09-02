"""运行中服务的学习与交易仿真端到端冒烟测试。"""
from __future__ import annotations

import httpx
from sqlalchemy import select

from app.common.auth import create_access_token
from app.db.database import SessionLocal
from app.db.models import SimulationSession, User


def main() -> None:
    db = SessionLocal()
    simulation_id = None
    try:
        user = db.execute(select(User).order_by(User.id)).scalars().first()
        if not user:
            raise RuntimeError("没有可用于冒烟测试的本地用户")
        token = create_access_token(user.id, user.username, user.role)
        client = httpx.Client(
            base_url="http://127.0.0.1:8000/api",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        try:
            guided = client.get("/study/guided")
            guided.raise_for_status()
            today = client.get("/study/today")
            today.raise_for_status()
            scenarios = client.get("/trade/sim/scenarios")
            scenarios.raise_for_status()
            created = client.post(
                "/trade/sim/sessions",
                json={"scenario_code": "day_ahead_retailer", "province": "山西"},
            )
            created.raise_for_status()
            task = created.json()
            simulation_id = task["id"]
            opened = client.post(f"/trade/sim/sessions/{simulation_id}/open")
            opened.raise_for_status()
            bids = [
                {
                    "period": period,
                    "segments": [
                        {"price": 500, "volume": 80},
                        {"price": 400, "volume": 20},
                    ],
                }
                for period in range(24)
            ]
            saved = client.put(
                f"/trade/sim/sessions/{simulation_id}/bids",
                json={"bids": bids},
            )
            saved.raise_for_status()
            for action in ("seal", "clear", "settle"):
                response = client.post(f"/trade/sim/sessions/{simulation_id}/{action}")
                response.raise_for_status()
                task = response.json()
            assert task["stage"] == "settled"
            assert len(task["settlement"]["periods"]) == 24
            print({
                "guided_units": len(guided.json()["units"]),
                "today_tasks": len(today.json()["tasks"]),
                "scenarios": len(scenarios.json()["scenarios"]),
                "final_stage": task["stage"],
                "settlement_periods": len(task["settlement"]["periods"]),
            })
        finally:
            client.close()
    finally:
        if simulation_id:
            row = db.get(SimulationSession, simulation_id)
            if row:
                db.delete(row)
                db.commit()
        db.close()


if __name__ == "__main__":
    main()
