"""Run synthetic multi-turn interviews against a configured cloud provider.

Credentials stay in a local JSON file or OPENINTERVIEW_LLM_* environment
variables. This makes paid requests and sends only the synthetic fixtures below.
Outputs contain model answers, decisions and latency, not a self-assessed quality score.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from openinterview_api.adapters.llm import build_llm_adapter  # noqa: E402
from openinterview_api.interview_engine import CampusInterviewEngine, InterviewConfig  # noqa: E402
from openinterview_api.services.question_bank import default_question_bank  # noqa: E402
from openinterview_api.services.semantic_interview import validate_cloud  # noqa: E402


PROJECT = """项目：订单查询系统（虚构测试项目）。候选人负责订单查询接口与 MySQL 联合索引优化。
Redis 缓存由同事负责。上线前 P95 800ms、后 200ms，但上线同时改了缓存，不能全部归因于索引。
两次压测 QPS 相同，数据量相同。候选人能解释执行计划、扫描行数和回表，未处理过线上缓存故障。
另一个校园活动项目使用 PostgreSQL，没有使用 Kafka。所有事实只用于本次合成评测。"""

SCENARIOS = {
    "knowledge": {
        "mode": "fundamentals", "resume": "", "question_id": "java-equals-hashcode-contract",
        "first_answer": "我认为两个对象 equals 返回 true 就足够了，即使 hashCode 不同，HashMap 也能找到它们。",
        "actor": "你是虚构的 Java 校招候选人。最初混淆 equals 与 hashCode；被追问查找过程后会纠正：先定位桶再比较 equals。后续承认曾忽略可变字段作为 key 的风险。不要直接背完整满分答案，每次最多100字，回应当前问题。",
        "review": ["是否发现最初的错误命题", "是否用查找流程或反例验证", "纠正后是否更新评价", "是否避免重复已回答内容"],
    },
    "project": {
        "mode": "project_deep_dive", "resume": PROJECT,
        "first_answer": "我负责订单查询优化，给 MySQL 加了联合索引，上线后 P95 从800ms降到了200ms。",
        "actor": "你是虚构候选人。严格依据项目事实回应当前问题；不要编造新指标、职责或故障。被问缓存时明确是同事负责；被问归因时承认同时改了缓存，不能把全部收益归因于自己。每次最多100字。项目事实：" + PROJECT,
        "review": ["是否围绕具体改动或效果归因", "是否区分本人和同事职责", "是否避免混用两个项目", "是否将信息不足当成待澄清而非造假"],
    },
}


def run_case(name, scenario, providers, rounds):
    engine = CampusInterviewEngine()
    session = engine.start(InterviewConfig(direction_id="backend", difficulty_id="campus",
        mode_id=scenario["mode"], resume_text=scenario["resume"],
        interview_strategy="semantic", provider_config=providers))["session"]
    if scenario.get("question_id"):
        card = default_question_bank().get_question(scenario["question_id"])
        session.current_question = card["prompt"]
        session.current_question_meta = {**card, "phase": "fundamentals"}
    actor = build_llm_adapter(providers)
    actor_messages = [{"role": "system", "content": scenario["actor"]}]
    result = {"scenario": name, "synthetic": True, "status": "running", "turns": [],
              "human_review_questions": scenario["review"]}
    for index in range(rounds):
        question = session.current_question
        actor_messages.append({"role": "user", "content": question})
        try:
            answer = scenario["first_answer"] if index == 0 else actor.complete(actor_messages, temperature=0.3)
            actor_messages.append({"role": "assistant", "content": answer})
            started = perf_counter()
            payload = engine.answer(session, answer)
            result["turns"].append({"question": question, "answer": answer,
                "decision_ms": round((perf_counter() - started) * 1000, 2),
                "decision": session.history[-1].question_meta["semantic_assessment"],
                "next_question": payload["next_question"], "state_revision": session.semantic_state["revision"]})
            print(f"{name}: completed turn {index + 1}", flush=True)
            if payload["is_finished"]:
                break
        except Exception as exc:
            result["status"] = "invalid_run"
            result["error_type"] = type(exc).__name__
            result["reason_code"] = getattr(exc, "reason_code", "request_error")
            result["failure_stage"] = "candidate_or_interviewer_request"
            return result
    result["status"] = "completed"
    result["final_state"] = session.semantic_state
    result["report"] = engine.report(session)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Local JSON with api_base/model/api_key (never committed)")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--scenario", choices=["all", "knowledge", "project"], default="all")
    parser.add_argument("--output", type=Path, default=ROOT / "logs/semantic-interview-evaluation.json")
    args = parser.parse_args()
    if not 1 <= args.rounds <= 8:
        parser.error("rounds must be between 1 and 8")
    settings = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {
        "api_base": os.environ.get("OPENINTERVIEW_LLM_API_BASE", ""),
        "model": os.environ.get("OPENINTERVIEW_LLM_MODEL", ""),
        "api_key": os.environ.get("OPENINTERVIEW_LLM_API_KEY", ""),
    }
    providers = {"llm": {"provider": "openai_compatible", **settings}}
    try:
        validate_cloud(providers)
    except ValueError:
        parser.error("Provide local --config or OPENINTERVIEW_LLM_API_BASE/MODEL/API_KEY; no real cloud test was run.")
    results = [run_case(name, scenario, providers, args.rounds) for name, scenario in SCENARIOS.items()
               if args.scenario in {"all", name}]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"model": settings["model"], "cases": results,
        "note": "Synthetic caller; manually review transcript relevance, corrections, grounding and depth. Completion is not a quality pass."},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {args.output}")
    return 0 if all(r["status"] == "completed" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
