import json
from openai import OpenAI
from neo4j import GraphDatabase
from typing import Optional, Any


OPENAI_API_KEY = "sk-af0bd19b890d465ea71ca754cf2a6658"
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "1234abcd"


class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )

    def call_llm(self, model, messages, temperature=0, max_tokens=1500):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        ).choices[0].message.content


class KGClient:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def read(self, query: str, params: Optional[dict]=None) -> Optional[list[dict]]:
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    
    def get_event_chain(self, system: str, event: str) -> Optional[list[dict]]:
        query = """
        MATCH (s:System {name: $system})
        MATCH (s)-[:HAS_EVENT]->(e:Event {name: $event})
        MATCH (e)-[:HAS_CAUSE]->(c:Cause)
        MATCH (c)-[:HAS_SUBCAUSE]->(sc:SubCause)
        MATCH (sc)-[:CAN_BE_REPAIRED_BY]->(r:Repair)
        MATCH (r)-[:NEED_TO_BE_VALIDATED_BY]->(v:Validation)
        RETURN e AS event, c AS cause, sc AS subcause, r AS repair, v AS validation

        UNION

        MATCH (s:System {name: $system})
        MATCH (s)-[:HAS_EVENT]->(e:Event {name: $event})
        MATCH (e)-[:HAS_CAUSE]->(c:Cause)
        MATCH (c)-[:CAN_BE_REPAIRED_BY]->(r:Repair)
        MATCH (r)-[:NEED_TO_BE_VALIDATED_BY]->(v:Validation)
        RETURN e AS event, c AS cause, NULL AS subcause, r AS repair, v AS validation
        """
        return self.read(query, {"system": system, "event": event})


class Coordinator:
    def __init__(self, event: str, model: str="qwen3-max", retry_times: int=3):
        self.llm_client = LLMClient()
        self.model = model
        self.retry_times = retry_times
        
        self.event = event

        system_prompt = "你是一个卫星运维专家，你的任务是：对捕获的卫星异常事件（Event）进行故障排查和修复。深呼吸，一步一步来。"
        self.history = [{"role": "system", "content": system_prompt}]  # 考虑缓存管理

        self.prompt_template = """Event:{event}
参考资料:{knowledge}
当前环节:基于参考资料将该异常初步归因到以下分系统中的一个：
结构, 载荷, 电源, 热控, 姿轨控制, 测控与数据处理
只输出分系统名称，不需要多余解释和格式"""
        self.prompt = self.prompt_template.format(event=self.event, knowledge=self._get_knowledge())

        self.sub_systems = {"结构", "载荷", "电源", "热控", "姿轨控制", "测控与数据处理"}

    def _get_knowledge(self) -> str:
        # 考虑RAG
        return """1.卫星由多个分系统组成，包括结构、载荷、电源、热控、姿轨控制、测控与数据处理。
2.结构分系统：功能:提供卫星的物理支撑保护内部设备免受发射振动、太空环境的影响。组成:框架、外壳、支架等轻量化高强度材料(如碳纤维、铝合金)
3.载荷分系统：功能:执行卫星的核心任务如通信、遥感、导航、科学探测等)组成:相机、雷达、通信转发器、科学仪器等。
4.电源分系统：功能:为全卫星供电并管理能源。组成:太阳能电池板(主能源)、蓄电池、电源控制与分配单元。
5.热控分系统：功能:维持设备在适宜温度范围(-40°C至+50°C)防止过热或过冷失效。方式:被动:隔热层、热反射涂层、热管。主动:电加热器、散热器。
6.姿轨控制分系统：功能:控制卫星在太空中的姿态(指向方向)和稳定性。组成:传感器:陀螺仪、星敏感器、太阳敏感器。执行机构:反作用轮、磁力矩器推进器。
7.测控与数据处理分系统：功能:处理卫星内部数据、协调各分系统工作、接收地面指令、向地面发送卫星状态数据和载荷数据组成:天线、收发机、数据存储设备中央计算、总线、接口模块"""

    def _check_format(self, response: str) -> bool:
        return response in self.sub_systems

    def route(self) -> str:
        self.history.append({"role": "user", "content": self.prompt})
        
        llm_response = self.llm_client.call_llm(model=self.model, messages=self.history).strip()
        retry_count = 0
        while not self._check_format(llm_response) and retry_count < self.retry_times:
            llm_response = self.llm_client.call_llm(
                model=self.model,
                messages=self.history + [
                    {"role": "assistant", "content": llm_response},
                    {"role": "user", "content": "解析失败，只输出分系统名称，不需要多余解释和格式"}
                ]
            ).strip()
            retry_count += 1
        if retry_count == self.retry_times and not self._check_format(llm_response):
            llm_response = "电源"  # 兜底
        self.history.append({"role": "assistant", "content": llm_response})
        
        return llm_response


# class WorkerNode:
#     def __init__(self, name: str, parent: Optional["WorkerNode"], children: Optional[list]=None, attribute: Optional[dict]=None):
#         self.name = name
#         self.parent = parent
#         self.children = children
#         self.attribute = attribute

#     def get_name(self) -> str:
#         return self.name
    
#     def get_parent(self) -> Optional["WorkerNode"]:
#         return self.parent

#     def add_children(self, children: list):
#         if not self.children:
#             self.children = []
#         self.children.extend(children.copy())

#     def get_children(self) -> Optional[list]:
#         return self.children

#     def set_attribute(self, key: str, value: Any):
#         if not self.attribute:
#             self.attribute = {}
#         self.attribute[key] = value

#     def get_attribute(self) -> Optional[dict]:
#         return self.attribute


# class Worker:
#     def __init__(self, excel_at: str, event: str, model: str="qwen3-max", retry_times: int=3):
#         self.llm_client = LLMClient()
#         self.model = model
#         self.retry_times = retry_times

#         self.kg_client = KGClient()
        
#         # 图谱管理 (More: 大模型探索能力/持久化经验reflection)
#         self.event = event
#         self.root = WorkerNode(name=self.event, parent=None, attribute={"type": "event"})
#         self.cursor = self.root
        
#         # 对话管理 (More: 记忆管理)
#         system_prompt = f"你是一个精通{excel_at}的卫星运维专家，你的任务是：对捕获的卫星异常事件（Event）进行故障排查和修复。深呼吸，一步一步来。"
#         self.history = [{"role": "system", "content": system_prompt}]

#         self.prompt_template = """Event:{event}
# 实时遥测:{telemetry_block}
# 知识图谱:{kg_block}
# 具体任务:{instruction_block}
# 要求:{format_block}"""

#     def _get_telemetry_block(self):
#         # 演示需要，进行简化
#         import json
#         return json.dumps({
#             "battery_voltage_last10_mean": 26.3,
#             "array_power_last10_mean": 132.0,
#             "battery_temp_last10_min": 11,
#             "bus_current_sensor_bias": "suspected",
#         }, ensure_ascii=False, indent=2)

#     def _get_kg_block(self):
#         pass

#     def _get_instruction_block(self):
#         pass

#     def _get_format_block(self):
#         # 演示需要，进行简化
#         return "只输出编号，不需要多余解释和格式"

#     def run(self):
#         # LOOP
#         pass


class Worker:
    def __init__(self, excel_at: str, system: str, event: str, model: str="qwen3-max", retry_times: int=3):
        self.llm_client = LLMClient()
        self.model = model
        self.retry_times = retry_times

        self.kg_client = KGClient()
        
        self.system = system
        self.event = event
        
        system_prompt = f"你是一个精通{excel_at}的卫星运维专家，你的任务是：对捕获的卫星异常事件（Event）进行故障排查和修复。深呼吸，一步一步来。"
        self.history = [{"role": "system", "content": system_prompt}]

        self.prompt_template = """Event:{event}
实时遥测:{telemetry_block}
知识图谱:{kg_block}
具体任务:{instruction_block}
要求:{format_block}"""

    def _get_telemetry_block(self) -> str:
        return """{
  "timestamp": "2025-11-20T23:47:12Z",
  "event_detected": "母线电压异常",
  "system": "电源分系统",
  "telemetry": {
    "bus_voltage": {
      "value": 31.4,
      "unit": "V",
      "nominal": 28.0,
      "deviation_percent": 12.1,
      "status": "out_of_range"
    },
    "bus_current": {
      "value": 9.8,
      "unit": "A",
      "nominal": 8.5,
      "fluctuation_ripple": 0.42,
      "status": "unstable"
    },
    "dcdc_output_voltage": {
      "module_id": "DCDC-1A",
      "value": 29.7,
      "unit": "V",
      "nominal": 28.0,
      "drift_detected": true
    },
    "dcdc_temperature": {
      "value": 72.5,
      "unit": "C",
      "nominal": 55.0,
      "limit": 80.0,
      "status": "warning"
    },
    "pcu_status": {
      "voltage_reg_fail_count": 7,
      "last_fail_timestamp": "2025-11-20T23:45:03Z",
      "mode": "regulation_fault"
    },
    "fault_flags": {
      "bus_overvoltage": true,
      "dcdc_drift_flag": true,
      "load_surge_detected": false
    }
  }
}"""

    def _get_kg_block(self) -> str:
        # 假设在图谱中有名称与self.event相同的节点
        kg = self.kg_client.get_event_chain(system=self.system, event=self.event)

        if not kg:
            return """未检索到知识图谱"""
        
        paths = []
        for row in kg:
            e = row["event"]
            c = row["cause"]
            sc = row["subcause"]
            r = row["repair"]
            v = row["validation"]
            if sc:
                path = (
                    f"{e} ->HAS_CAUSE-> {c} "
                    f"->HAS_SUBCAUSE-> {sc} "
                    f"->CAN_BE_REPAIRED_BY-> {r} "
                    f"->NEED_TO_BE_VALIDATED_BY-> {v}"
                )
            else:
                path = (
                    f"{e} ->HAS_CAUSE-> {c} "
                    f"->CAN_BE_REPAIRED_BY-> {r} "
                    f"->NEED_TO_BE_VALIDATED_BY-> {v}"
                )
            paths.append(path)

        return "\n".join(paths)

    def _get_instruction_block(self) -> str:
        return """基于知识图谱的候选路径，产出有约束、可执行的修复建议列表。"""

    def _get_format_block(self) -> str:
        return """1) 根据候选路径与常识，给出排序后的修复建议清单（top 3 即可）。每条建议需包含：
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

只返回 JSON，不要多余文字。"""

    def _get_prompt(self) -> str:
        return self.prompt_template.format(event=self.event, telemetry_block=self._get_telemetry_block(), kg_block=self._get_kg_block(), instruction_block=self._get_instruction_block(), format_block=self._get_format_block())

    def _check_format(self, response: str) -> bool:
        try:
            json.loads(response)
        except json.JSONDecodeError:
            return False
        finally:
            return True

    def run(self):
        prompt = self._get_prompt()
        self.history.append({"role": "user", "content": prompt})

        llm_response = self.llm_client.call_llm(model=self.model, messages=self.history).strip()
        retry_count = 0
        while not self._check_format(llm_response) and retry_count < self.retry_times:
            llm_response = self.llm_client.call_llm(
                model=self.model,
                messages=self.history + [
                    {"role": "assistant", "content": llm_response},
                    {"role": "user", "content": "解析失败，只返回 JSON，不要多余文字。"}
                ]
            ).strip()
            retry_count += 1
        if retry_count == self.retry_times and not self._check_format(llm_response):
            raise json.JSONDecodeError
        self.history.append({"role": "assistant", "content": llm_response})
        
        return llm_response


def run(event: str):
    router = Coordinator(event)
    result = router.route()
    print("⚠️  event:", event)
    print("🚀  route to:", result)

    energy_worker = Worker(excel_at="电源分系统", system="电源分系统", event=event)
    result = energy_worker.run()
    print("🚩  result:", result)


if __name__ == "__main__":
    run("能源系统供电异常")