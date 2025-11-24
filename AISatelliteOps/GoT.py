# -*- coding: utf-8 -*-
"""
从知识图谱抽取 → 大模型CoT推理 → 推荐修复动作（Qwen/OpenAI兼容）
依赖: pip install neo4j openai (>=1.0)
环境变量:
  OPENAI_API_KEY=你的密钥
  OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1    # (Qwen 兼容端点)
  QWEN_MODEL=qwen3-max
"""

import os
import json
from typing import List, Dict, Any, Tuple
from neo4j import GraphDatabase
from openai import OpenAI

os.environ["OPENAI_API_KEY"] = "sk-af0bd19b890d465ea71ca754cf2a6658"
os.environ["OPENAI_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
os.environ["QWEN_MODEL"] = "qwen3-max"
# -------------------------------
# 1) Neo4j 访问与抽取
# -------------------------------
class KGClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def fetch_event_paths(self, event_name: str) -> List[Dict[str, str]]:
        """
        抽取事件 -> 原因 -> 子原因 -> 修复 的所有可达路径。
        若没有子原因，仍返回直接修复（如果图谱设计有直接原因->修复）。
        """
        cypher = """
        MATCH (e:Event {name:$event})-[:HAS_CAUSE]->(c:Cause)
        OPTIONAL MATCH (c)-[:HAS_SUB_CAUSE]->(s:SubCause)
        OPTIONAL MATCH (s)-[:LEADS_TO_REPAIR]->(r:Repair)
        OPTIONAL MATCH (c)-[:LEADS_TO_REPAIR]->(r2:Repair)
        WITH e,c,s,coalesce(r,r2) AS rr
        RETURN e.name AS event, c.name AS cause, 
               coalesce(s.name,'无子原因') AS sub_cause,
               coalesce(rr.name,'无修复方案') AS repair
        ORDER BY cause, sub_cause
        """
        with self.driver.session() as session:
            recs = session.run(cypher, event=event_name)
            rows = [dict(r) for r in recs]
        # 过滤掉“无修复方案”的空路径
        return [r for r in rows if r["repair"] != "无修复方案"]

    def write_proposed_repairs(self, event_name: str, proposals: List[Dict[str, Any]]) -> None:
        """
        可选：把推荐修复动作回写到图谱，创建/更新 PROPOSED_REPAIR 关系。
        PROPOSED_REPAIR 包含 score、confidence、rationale(短) 等属性。
        """
        with self.driver.session() as session:
            for p in proposals:
                repair = p.get("repair_action")
                if not repair:
                    continue
                score = float(p.get("score", 0.0))
                conf  = float(p.get("confidence", 0.0))
                why   = p.get("brief_reason", "")
                session.run(
                    """
                    MATCH (e:Event {name:$event})
                    MERGE (r:Repair {name:$repair})
                    MERGE (e)-[rel:PROPOSED_REPAIR]->(r)
                    SET rel.score=$score, rel.confidence=$conf, rel.brief_reason=$why, rel.updated=timestamp()
                    """,
                    event=event_name, repair=repair, score=score, conf=conf, why=why
                )


# -------------------------------
# 2) LLM 封装（Qwen/OpenAI兼容）
# -------------------------------
class LLM:
    def __init__(self):
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        api_key  = os.getenv("OPENAI_API_KEY", "").strip()
        model    = os.getenv("QWEN_MODEL", "qwen3-max").strip()
        if not api_key:
            raise RuntimeError("未设置 OPENAI_API_KEY 环境变量")
        if not base_url:
            raise RuntimeError("未设置 OPENAI_BASE_URL 环境变量（如 Qwen 兼容端点）")
        self.model  = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _build_prompt(event: str, paths: List[Dict[str, str]], extra_telemetry: Dict[str, Any] = None) -> str:
        """
        将图谱路径组织为结构化上下文；可选拼接最新遥测摘要。
        """
        graph_lines = []
        for r in paths:
            graph_lines.append(f"- {r['cause']} → {r['sub_cause']} → {r['repair']}")
        graph_block = "\n".join(graph_lines) if graph_lines else "(无候选路径)"

        telemetry_block = ""
        if extra_telemetry:
            telemetry_block = "最新遥测概要:\n" + json.dumps(extra_telemetry, ensure_ascii=False, indent=2)

        # 设计成结构化决策，不暴露思维链细节（让模型内部推理，但只输出结构化字段）
        prompt = f"""
你是航天能源运维专家。基于“事件→原因→子原因→修复”的图谱候选，产出有约束、可执行的修复建议列表。
事件: {event}

图谱候选路径:
{graph_block}

{telemetry_block}

要求：
1) 根据候选路径与常识，给出排序后的修复建议清单（top 3 即可）。每条建议需包含：
   - repair_action: 具体修复动作（严格对应上述候选或其等价工程表述）
   - target_nodes: 涉及的原因/子因子（列表）
   - preconditions: 执行该动作的前置条件或适用场景（列表）
   - verification_metrics: 修复后需重点观测的验证指标（列表）
   - confidence: [0,1] 信心度（考虑该路径与遥测是否吻合）
   - score: [0,1] 综合评分（兼顾收益/风险/可实施性）
   - brief_reason: 1-2 句简短理由（不要展开思维链细节）

2) 全量返回 JSON，字段：
{{
  "event": "...",
  "recommendations": [
     {{
       "repair_action": "...",
       "target_nodes": ["cause/sub-cause", "..."],
       "preconditions": ["..."],
       "verification_metrics": ["..."],
       "confidence": 0-1,
       "score": 0-1,
       "brief_reason": "..."
     }}
  ]
}}

只返回 JSON，不要多余文字。
"""
        return prompt

    def recommend(self, event: str, paths: List[Dict[str, str]], extra_telemetry: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        调用大模型生成结构化推荐。
        """
        prompt = self._build_prompt(event, paths, extra_telemetry)
        print(prompt)
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "你是严谨的航天能源运维专家。严格按JSON结构输出，不要解释文字。"},
                {"role": "user", "content": prompt}
            ],
        )
        try:
            data = json.loads(resp.choices[0].message.content)
        except Exception:
            # 兜底：若解析失败，给出空结构
            data = {"event": event, "recommendations": []}
        return data


# -------------------------------
# 3) 端到端流程
# -------------------------------
def run_pipeline(
    event_name: str,
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_password: str = "neo4j_password_here",
    extra_telemetry: Dict[str, Any] = None,
    write_back: bool = True
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """
    端到端：从图谱抽取 → LLM 推理 → (可选)写回推荐。
    返回：(paths, llm_output)
    """
    # 1) 抽取图谱路径
    kg = KGClient(neo4j_uri, neo4j_user, neo4j_password)
    paths = kg.fetch_event_paths(event_name)
    if not paths:
        print("⚠️ 图谱中没有找到可用的候选路径，请先构建或检查数据。")
        return [], {"event": event_name, "recommendations": []}

    # 2) LLM 推荐
    llm = LLM()
    rec = llm.recommend(event_name, paths, extra_telemetry=extra_telemetry)

    # 3) 可选：写回图谱
    if write_back and rec.get("recommendations"):
        kg.write_proposed_repairs(event_name, rec["recommendations"])

    return paths, rec


# -------------------------------
# 4) 演示
# -------------------------------
if __name__ == "__main__":
    # 示例事件名（确保你的图谱中存在该事件及其下游关系）
    EVENT = "卫星能源系统供电异常"

    # （可选）拼接一些最近遥测摘要，帮助模型判断信心度/前置条件
    telemetry_summary = {
        "battery_voltage_last10_mean": 26.3,
        "array_power_last10_mean": 132.0,
        "battery_temp_last10_min": 11,
        "bus_current_sensor_bias": "suspected",
    }

    # 运行流程
    paths, result = run_pipeline(
        event_name=EVENT,
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="1234abcd",   # ← 修改为你的密码
        extra_telemetry=telemetry_summary,
        write_back=True
    )

    # 打印结果
    print("\n=== 候选路径（来自图谱）===")
    for p in paths:
        print(f"- {p['cause']} → {p['sub_cause']} → {p['repair']}")

    print("\n=== LLM 推荐结果（JSON）===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
