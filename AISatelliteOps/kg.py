from neo4j import GraphDatabase


NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "1234abcd"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


KG = {
    "system": "电源分系统",
    "events": {
        "母线电压异常": {
            "母线电压调节失灵": {
                "DC-DC模块漂移/失效": ("重置并切换到冗余电源单元", "母线电压恢复并稳定在额定范围"),
                "参考电压源故障": ("重启电源控制单元（软重启/硬重启）", "母线电压恢复并稳定在额定范围")
            },
            "电压瞬变/尖峰": {
                "开关切换干扰": ("重标定电压/电流采样通道", "母线电压恢复并稳定在额定范围"),
                "外部放电事件（弧光/等离子）": ("地面命令执行紧急断路/熔断保护", "母线电流恢复正常且无超限脉动")
            },
            "母线接地/漏电": ("切换旁路/隔离故障段（断开短路段）", "故障段电流降为零且负载恢复")
        },
        "电池性能下降/容量衰减": {
            "电池老化": {
                "循环寿命到期": ("执行电池均衡/重校准程序", "电池端电压/荷电状态（SoC）按预期曲线恢复"),
                "温度异常加速老化": ("启动电池加热或降温模式（温控策略）", "温度回到安全区间并稳定")
            },
            "电池单体失效": ("隔离失效单体并切换冗余单体", "电池端电压/荷电状态（SoC）按预期曲线恢复")
        },
        "太阳能阵列发电异常": {
            "光电池输出下降": {
                "太阳翼未展开或角度异常": ("展开/复位太阳翼并执行展开复位程序", "太阳阵输出功率恢复至预期百分比（例如 >90% 额定）"),
                "光电池污染或退化": ("启动阵面抖动清理或去污程序", "太阳阵输出功率恢复至预期百分比（例如 >90% 额定）")
            },
            "阵列馈电断路": ("检查并切换阵列馈电开关/继电器到冗余回路", "母线电压恢复并稳定在额定范围")
        },
        "过流/短路": {
            "瞬时大电流/继电器粘连": ("切换旁路/隔离故障段（断开短路段）", "母线电流恢复正常且无超限脉动"),
            "组件内部短路": {
                "电缆绝缘破损": ("隔离故障段并回退至冗余线路", "故障段电流降为零且负载恢复"),
                "功率电子器件失效": ("切换到冗余功率变换模块并回收故障器件遥测", "母线电压恢复并稳定在额定范围")
            }
        },
        "充放电控制异常": {
            "充电控制失灵": {
                "最大充电限幅器失效": ("调整充电策略并重标定充电限幅器参数", "电池端电压/荷电状态（SoC）按预期曲线恢复"),
                "均衡电路断开": ("执行电池均衡/重校准程序", "电池端电压/荷电状态（SoC）按预期曲线恢复")
            },
            "放电路径异常": ("手动/自动隔离异常负载并重分配负载策略", "母线电流恢复正常且无超限脉动")
        },
        "电源控制单元（PCU）异常": {
            "控制器死机/重启循环": ("重启电源控制单元（软重启/硬重启）并回退到稳定固件版本", "地链通信与指令回执确认恢复"),
            "单事件翻转（SEU）引起功能异常": ("启用容错校验并切换冗余控制器路径", "地链通信与指令回执确认恢复")
        },
        "遥测/测量异常（电压/电流显示不可信）": {
            "传感器误差/ADC漂移": ("重标定电压/电流采样通道", "遥测中相关采样通道误差下降到可接受范围（偏差 < 指定阈值）"),
            "遥测编码/解码错误": ("重发或修正地面下发控制指令并校验回传", "地链通信与指令回执确认恢复")
        },
        "热失控（电源相关）": {
            "功率转换单元过热": ("启动被动/主动散热或降额工作，并切换冗余模块", "温度回到安全区间并稳定"),
            "电池热失控": ("紧急隔离故障电池组并进入安全模式", "温度回到安全区间并稳定且无温度上升趋势")
        }
    }
}


def clear_db(tx):
    tx.run("MATCH (n) DETACH DELETE n")

def create_constraints(tx):
    labels = ["System", "Event", "Cause", "SubCause", "Repair", "Validation"]
    for lab in labels:
        try:
            tx.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{lab}) REQUIRE n.name IS UNIQUE")
        except Exception:
            try:
                tx.run(f"CREATE CONSTRAINT FOR (n:{lab}) REQUIRE n.name IS UNIQUE")
            except Exception:
                pass

def merge_node(tx, label, name, props=None):
    p = {"name": name}
    if props:
        p.update(props)
    tx.run(f"MERGE (n:{label} {{name:$name}}) SET n += $props", name=name, props=p)

def create_rel(tx, a_label, a_name, rel, b_label, b_name):
    tx.run(
        f"""
        MATCH (a:{a_label} {{name:$a_name}}), (b:{b_label} {{name:$b_name}})
        MERGE (a)-[r:{rel}]->(b)
        """,
        a_name=a_name, b_name=b_name
    )

def process_kg(tx, kg):
    system_name = kg["system"]
    merge_node(tx, "System", system_name)

    for event_name, event_content in kg["events"].items():
        merge_node(tx, "Event", event_name)
        create_rel(tx, "System", system_name, "HAS_EVENT", "Event", event_name)

        for cause_name, cause_val in event_content.items():
            merge_node(tx, "Cause", cause_name)
            create_rel(tx, "Event", event_name, "HAS_CAUSE", "Cause", cause_name)

            # 无subcause
            if isinstance(cause_val, tuple) and len(cause_val) == 2:
                repair, validation = cause_val
                merge_node(tx, "Repair", repair)
                merge_node(tx, "Validation", validation)
                create_rel(tx, "Cause", cause_name, "CAN_BE_REPAIRED_BY", "Repair", repair)
                create_rel(tx, "Repair", repair, "NEED_TO_BE_VALIDATED_BY", "Validation", validation)
            
            # 有subcause
            elif isinstance(cause_val, dict):
                for sub_name, sub_val in cause_val.items():
                    merge_node(tx, "SubCause", sub_name)
                    create_rel(tx, "Cause", cause_name, "HAS_SUBCAUSE", "SubCause", sub_name)
                    
                    if isinstance(sub_val, tuple) and len(sub_val) == 2:
                        repair, validation = sub_val
                        merge_node(tx, "Repair", repair)
                        merge_node(tx, "Validation", validation)
                        create_rel(tx, "SubCause", sub_name, "CAN_BE_REPAIRED_BY", "Repair", repair)
                        create_rel(tx, "Repair", repair, "NEED_TO_BE_VALIDATED_BY", "Validation", validation)
                    else:
                        pass
            else:
                pass


def main():
    with driver.session() as session:
        print("1-清空已有节点和关系")
        session.write_transaction(clear_db)

        print("2-创建唯一约束")
        session.write_transaction(create_constraints)

        print("3-创建知识图谱")
        session.write_transaction(process_kg, KG)


if __name__ == "__main__":
    main()