# -*- coding: utf-8 -*-
"""
卫星能源系统运维知识图谱（Knowledge Graph）
功能：创建卫星能源系统知识图谱（事件→原因→子原因→修复→验证）
"""

from neo4j import GraphDatabase
# ==================================================
# 1. 图谱类定义
# ==================================================
class KnowledgeGraph:
    def __init__(self, uri, user, password):
        """初始化数据库连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    # ----------------------------------------------
    # 创建节点与关系
    # ----------------------------------------------
    def create_nodes(self):
        with self.driver.session() as session:
            print("🧩 清空数据库 ...")
            session.run("MATCH (n) DETACH DELETE n")

            # === 事件层 ===
            print("📍 创建事件节点 ...")
            session.run("CREATE (e:Event {name:'卫星能源系统供电异常'})")

            # === 原因层 ===
            print("📍 创建原因节点 ...")
            causes = [
                '电池组异常',
                '太阳能电池阵异常',
                '电源控制分系统异常',
                '地面运控系统干预'
            ]
            for c in causes:
                session.run("CREATE (:Cause {name:$name})", name=c)

            # === 子原因层 ===
            print("📍 创建子原因节点 ...")
            sub_causes = [
                '电池单体失效',
                '电池温度过低',
                '电池均衡控制失灵',
                '光照遮挡',
                '电池片污染或退化',
                '驱动机构卡滞未完全展开',
                '功率转换单元过热',
                '电压调节模块漂移',
                '母线电流采样失准',
                '指令延迟或误下发',
                '地面遥测数据解码错误'
            ]
            for s in sub_causes:
                session.run("CREATE (:SubCause {name:$name})", name=s)

            # === 修复措施层 ===
            print("📍 创建修复措施节点 ...")
            repairs = [
                '启动电池加热模式',
                '重新分配充放电任务',
                '执行电池重校准程序',
                '重新定向姿态以优化光照',
                '启动阵面除污/抖动清理程序',
                '执行太阳翼展开复位',
                '启动冗余功率变换模块',
                '调整母线负载分配策略',
                '重新标定电压电流传感器',
                '重发控制指令并校验回传',
                '重新同步卫星与地面时标'
            ]
            for r in repairs:
                session.run("CREATE (:Repair {name:$name})", name=r)

            # === 验证层 ===
            print("📍 创建验证节点 ...")
            validations = ['地链通信恢复', '电压恢复正常', '信号强度恢复']
            for v in validations:
                session.run("CREATE (:Validation {name:$name})", name=v)

            # === 创建层级关系 ===
            print("🔗 建立层级关系 ...")
            # 事件→原因
            session.run("""
                MATCH (e:Event {name:'卫星能源系统供电异常'}),
                      (c1:Cause {name:'电池组异常'}),
                      (c2:Cause {name:'太阳能电池阵异常'}),
                      (c3:Cause {name:'电源控制分系统异常'}),
                      (c4:Cause {name:'地面运控系统干预'})
                CREATE (e)-[:HAS_CAUSE]->(c1),
                       (e)-[:HAS_CAUSE]->(c2),
                       (e)-[:HAS_CAUSE]->(c3),
                       (e)-[:HAS_CAUSE]->(c4)
            """)

            # 原因→子原因
            session.run("""
                MATCH (c1:Cause {name:'电池组异常'}),
                      (c2:Cause {name:'太阳能电池阵异常'}),
                      (c3:Cause {name:'电源控制分系统异常'}),
                      (c4:Cause {name:'地面运控系统干预'}),
                      (s1:SubCause {name:'电池单体失效'}),
                      (s2:SubCause {name:'电池温度过低'}),
                      (s3:SubCause {name:'电池均衡控制失灵'}),
                      (s4:SubCause {name:'光照遮挡'}),
                      (s5:SubCause {name:'电池片污染或退化'}),
                      (s6:SubCause {name:'驱动机构卡滞未完全展开'}),
                      (s7:SubCause {name:'功率转换单元过热'}),
                      (s8:SubCause {name:'电压调节模块漂移'}),
                      (s9:SubCause {name:'母线电流采样失准'}),
                      (s10:SubCause {name:'指令延迟或误下发'}),
                      (s11:SubCause {name:'地面遥测数据解码错误'})
                CREATE (c1)-[:HAS_SUB_CAUSE]->(s1),
                       (c1)-[:HAS_SUB_CAUSE]->(s2),
                       (c1)-[:HAS_SUB_CAUSE]->(s3),
                       (c2)-[:HAS_SUB_CAUSE]->(s4),
                       (c2)-[:HAS_SUB_CAUSE]->(s5),
                       (c2)-[:HAS_SUB_CAUSE]->(s6),
                       (c3)-[:HAS_SUB_CAUSE]->(s7),
                       (c3)-[:HAS_SUB_CAUSE]->(s8),
                       (c3)-[:HAS_SUB_CAUSE]->(s9),
                       (c4)-[:HAS_SUB_CAUSE]->(s10),
                       (c4)-[:HAS_SUB_CAUSE]->(s11)
            """)

            # 子原因→修复
            session.run("""
                MATCH (s1:SubCause {name:'电池温度过低'}),
                      (s2:SubCause {name:'电池均衡控制失灵'}),
                      (s3:SubCause {name:'电池单体失效'}),
                      (s4:SubCause {name:'光照遮挡'}),
                      (s5:SubCause {name:'电池片污染或退化'}),
                      (s6:SubCause {name:'驱动机构卡滞未完全展开'}),
                      (s7:SubCause {name:'功率转换单元过热'}),
                      (s8:SubCause {name:'电压调节模块漂移'}),
                      (s9:SubCause {name:'母线电流采样失准'}),
                      (s10:SubCause {name:'指令延迟或误下发'}),
                      (s11:SubCause {name:'地面遥测数据解码错误'}),
                      (r1:Repair {name:'启动电池加热模式'}),
                      (r2:Repair {name:'重新分配充放电任务'}),
                      (r3:Repair {name:'执行电池重校准程序'}),
                      (r4:Repair {name:'重新定向姿态以优化光照'}),
                      (r5:Repair {name:'启动阵面除污/抖动清理程序'}),
                      (r6:Repair {name:'执行太阳翼展开复位'}),
                      (r7:Repair {name:'启动冗余功率变换模块'}),
                      (r8:Repair {name:'调整母线负载分配策略'}),
                      (r9:Repair {name:'重新标定电压电流传感器'}),
                      (r10:Repair {name:'重发控制指令并校验回传'}),
                      (r11:Repair {name:'重新同步卫星与地面时标'})
                CREATE (s1)-[:LEADS_TO_REPAIR]->(r1),
                       (s2)-[:LEADS_TO_REPAIR]->(r2),
                       (s3)-[:LEADS_TO_REPAIR]->(r3),
                       (s4)-[:LEADS_TO_REPAIR]->(r4),
                       (s5)-[:LEADS_TO_REPAIR]->(r5),
                       (s6)-[:LEADS_TO_REPAIR]->(r6),
                       (s7)-[:LEADS_TO_REPAIR]->(r7),
                       (s8)-[:LEADS_TO_REPAIR]->(r8),
                       (s9)-[:LEADS_TO_REPAIR]->(r9),
                       (s10)-[:LEADS_TO_REPAIR]->(r10),
                       (s11)-[:LEADS_TO_REPAIR]->(r11)
            """)

            # 修复→验证
            session.run("""
                MATCH (r1:Repair {name:'启动电池加热模式'}),
                      (r4:Repair {name:'重新定向姿态以优化光照'}),
                      (r7:Repair {name:'启动冗余功率变换模块'}),
                      (r10:Repair {name:'重发控制指令并校验回传'}),
                      (v1:Validation {name:'地链通信恢复'}),
                      (v2:Validation {name:'电压恢复正常'}),
                      (v3:Validation {name:'信号强度恢复'})
                CREATE (r1)-[:REQUIRES_VALIDATION]->(v2),
                       (r4)-[:REQUIRES_VALIDATION]->(v3),
                       (r7)-[:REQUIRES_VALIDATION]->(v2),
                       (r10)-[:REQUIRES_VALIDATION]->(v1)
            """)

            print("✅ 卫星能源系统知识图谱已成功创建。")

    # ----------------------------------------------
    # 查询函数
    # ----------------------------------------------
    def query(self, event_name):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:Event {name:$event_name})-[:HAS_CAUSE]->(c:Cause)
                OPTIONAL MATCH (c)-[:HAS_SUB_CAUSE]->(s:SubCause)-[:LEADS_TO_REPAIR]->(r:Repair)
                RETURN DISTINCT 
                    e.name AS event,
                    c.name AS cause,
                    coalesce(s.name, '无子原因') AS sub_cause,
                    coalesce(r.name, '无修复方案') AS repair
                ORDER BY cause, sub_cause
            """, event_name=event_name)
            return list(result)



# ==================================================
# 2. 主程序
# ==================================================
if __name__ == "__main__":
    uri = "bolt://localhost:7687"
    user = "neo4j"
    password = "1234abcd"

    kg = KnowledgeGraph(uri, user, password)
    print("🚀 开始构建卫星能源系统知识图谱 ...")
    kg.create_nodes()

    print("\n🔍 查询事件：卫星能源系统供电异常")
    results = kg.query("卫星能源系统供电异常")

    print("\n📘 查询结果：")
    for record in results:
        print(f"Event: {record['event']}, Cause: {record['cause']}, Sub-Cause: {record['sub_cause']}, Repair: {record['repair']}")
    print("\n✅ 查询完成。")
