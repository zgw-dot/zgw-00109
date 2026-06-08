"""
批次号唯一性回归测试
测试场景：同一秒内连续导入多个批次，验证批次号唯一性
"""

import requests
import time
import subprocess
import sys
import os
import signal

BASE_URL = "http://localhost:8000"


def print_step(step_no, title):
    print(f"\n{'=' * 70}")
    print(f"步骤 {step_no}: {title}")
    print(f"{'=' * 70}")


def print_response(response):
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        import json
        print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)[:800]}")
        return data
    except:
        print(f"响应: {response.text[:500]}")
        return None


def wait_for_service(timeout=30):
    """等待服务启动"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{BASE_URL}/api/templates", timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(0.5)
    return False


def start_service():
    """启动服务"""
    print("启动服务...")
    proc = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    if wait_for_service():
        print("✓ 服务已启动")
        return proc
    else:
        raise Exception("服务启动超时")


def stop_service(proc):
    """停止服务"""
    print("停止服务...")
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except:
        try:
            proc.kill()
        except:
            pass
    time.sleep(2)
    print("✓ 服务已停止")


def test_batch_no_uniqueness():
    print("\n" + "╔" + "═" * 70 + "╗")
    print("║" + " " * 10 + "批次号唯一性回归测试" + " " * 36 + "║")
    print("╚" + "═" * 70 + "╝")

    # 先检查服务是否已在运行
    service_running = False
    try:
        response = requests.get(f"{BASE_URL}/api/templates", timeout=2)
        if response.status_code == 200:
            service_running = True
            print("✓ 服务已在运行")
    except:
        pass

    proc = None
    if not service_running:
        proc = start_service()

    try:
        # 步骤1: 准备连续导入数据 - 先导入模板
        print_step(1, "同一秒内连续导入 - 先导入模板")

        template_import_data = {
            "templates": [
                {
                    "name": "唯一性测试-变压器巡检-V1",
                    "description": "批次号唯一性测试-变压器日常巡检模板",
                    "check_items": [
                        {"device_code": "TRANS-UNIQ-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"},
                        {"device_code": "TRANS-UNIQ-001", "item_name": "油位", "unit": "mm", "standard_value": "150-250", "tolerance": "±10"},
                        {"device_code": "TRANS-UNIQ-002", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                },
                {
                    "name": "唯一性测试-开关柜巡检-V1",
                    "description": "批次号唯一性测试-开关柜日常巡检模板",
                    "check_items": [
                        {"device_code": "SW-UNIQ-001", "item_name": "温度", "unit": "°C", "standard_value": "≤65", "tolerance": "±3"},
                        {"device_code": "SW-UNIQ-001", "item_name": "电流", "unit": "A", "standard_value": "≤1000", "tolerance": "±50"}
                    ]
                }
            ],
            "task_packages": [],
            "operator": "测试管理员-唯一性"
        }

        # 步骤2: 连续导入 - 先导入模板，立刻导入任务包（模拟同一秒内）
        print_step(2, "同一秒内连续导入 - 立刻导入任务包")

        # 连续发送两个请求，间隔极短（模拟同一秒内）
        print("正在连续发送两个导入请求...")
        response1 = requests.post(f"{BASE_URL}/api/batch/import/json", json=template_import_data)
        data1 = response1.json()

        # 从第一个响应中获取模板ID
        template_ids = {}
        for result in data1["results"]:
            if result["success"] and result["record_type"] == "template":
                template_ids[result["identifier"]] = int(result["message"].split("ID: ")[1])

        # 构建任务包导入数据（使用实际的template_id）
        package_import_data = {
            "templates": [],
            "task_packages": [
                {
                    "package_no": "PKG-UNIQ-TEST-001",
                    "template_id": template_ids["唯一性测试-变压器巡检-V1"],
                    "operator": "测试管理员-唯一性"
                },
                {
                    "package_no": "PKG-UNIQ-TEST-002",
                    "template_id": template_ids["唯一性测试-开关柜巡检-V1"],
                    "operator": "测试管理员-唯一性"
                }
            ],
            "operator": "测试管理员-唯一性"
        }

        # 极短间隔后发送第二个请求
        time.sleep(0.001)
        response2 = requests.post(f"{BASE_URL}/api/batch/import/json", json=package_import_data)

        data1 = print_response(response1)
        data2 = print_response(response2)

        # 验证两个请求都成功
        assert response1.status_code == 200, f"第一个导入请求失败: {response1.status_code}"
        assert response2.status_code == 200, f"第二个导入请求失败: {response2.status_code}"
        assert data1["success"] == True, f"第一个导入应成功: {data1.get('message')}"
        assert data2["success"] == True, f"第二个导入应成功: {data2.get('message')}"

        batch_no_1 = data1["batch_no"]
        batch_no_2 = data2["batch_no"]

        print(f"批次号1: {batch_no_1}")
        print(f"批次号2: {batch_no_2}")

        # 验证批次号不同
        assert batch_no_1 != batch_no_2, f"批次号应不同，但都是: {batch_no_1}"
        print("✓ 两个批次号不同，唯一性验证通过")

        # 验证批次号格式正确（包含毫秒和序号）
        assert batch_no_1.startswith("BATCH-"), f"批次号格式错误: {batch_no_1}"
        parts = batch_no_1.split("-")
        assert len(parts) == 3, f"批次号格式应为 BATCH-时间戳-序号: {batch_no_1}"
        assert len(parts[1]) == 17, f"批次号时间戳应包含毫秒: {batch_no_1}"
        assert parts[2].isdigit(), f"批次号序号应为数字: {batch_no_1}"
        print("✓ 批次号格式正确，包含毫秒和序号")

        # 步骤3: 验证数据正确导入
        print_step(3, "验证导入数据正确性")

        response = requests.get(f"{BASE_URL}/api/templates")
        templates = response.json()
        template_names = [t["name"] for t in templates]
        assert "唯一性测试-变压器巡检-V1" in template_names, "模板1未导入"
        assert "唯一性测试-开关柜巡检-V1" in template_names, "模板2未导入"
        print(f"✓ 模板导入正确，共 {len(templates)} 个模板")

        response = requests.get(f"{BASE_URL}/api/task-packages")
        packages = response.json()
        package_nos = [p["package_no"] for p in packages]
        assert "PKG-UNIQ-TEST-001" in package_nos, "任务包1未导入"
        assert "PKG-UNIQ-TEST-002" in package_nos, "任务包2未导入"
        print(f"✓ 任务包导入正确，共 {len(packages)} 个任务包")

        # 步骤4: 验证重复数据导入失败且不污染库
        print_step(4, "验证重复数据导入失败且不污染库")

        # 记录导入前的数量
        templates_before = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_before = len(requests.get(f"{BASE_URL}/api/task-packages").json())

        # 导入重复数据
        duplicate_data = {
            "templates": [
                {
                    "name": "唯一性测试-变压器巡检-V1",
                    "description": "重复导入测试",
                    "check_items": [
                        {"device_code": "TRANS-UNIQ-003", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                }
            ],
            "task_packages": [
                {
                    "package_no": "PKG-UNIQ-TEST-001",
                    "template_id": template_ids["唯一性测试-变压器巡检-V1"],
                    "operator": "测试管理员-唯一性"
                }
            ],
            "operator": "测试管理员-唯一性"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=duplicate_data)
        data = print_response(response)

        assert response.status_code == 200, "重复导入请求应成功返回"
        assert data["success"] == False, "重复导入应标记为失败"
        assert data["failed_count"] == 2, f"2条记录都应失败，实际: {data['failed_count']}"

        for result in data["results"]:
            assert result["success"] == False, f"记录 {result['identifier']} 应失败"
            assert "重复" in result["message"], f"错误应包含'重复': {result['message']}"
            assert len(result["errors"]) > 0, "应有详细错误信息"

        print(f"✓ 重复导入检测正常，失败批次号: {data['batch_no']}")

        # 验证数据库未被污染
        templates_after = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_after = len(requests.get(f"{BASE_URL}/api/task-packages").json())
        assert templates_after == templates_before, f"模板数量应保持为{templates_before}，实际: {templates_after}"
        assert packages_after == packages_before, f"任务包数量应保持为{packages_before}，实际: {packages_after}"
        print("✓ 数据库未被污染，数据完整性验证通过")

        # 步骤5: 批量导出验证
        print_step(5, "批量导出验证 - 包含批次号、状态、读数摘要")

        response = requests.get(f"{BASE_URL}/api/batch/export", params={"batch_no": batch_no_1})
        data = print_response(response)

        assert response.status_code == 200, "导出请求应成功"
        assert data["success"] == True, "导出应成功"
        assert data["export_count"] == 2, f"应导出2个模板，实际: {data['export_count']}"

        for item in data["items"]:
            assert item["batch_no"] == batch_no_1, f"批次号应匹配: {item['batch_no']} != {batch_no_1}"
            assert "import_batch" in item, "应包含导入批次信息"
            assert item["import_batch"]["batch_no"] == batch_no_1, "导入批次信息应正确"
            assert "current_status" in item, "应包含当前状态"
            assert "data" in item, "应包含实体数据"
        print("✓ 导出数据格式正确，包含批次信息")

        # 步骤6: 审计日志验证 - 按批次查询
        print_step(6, "审计日志验证 - 按批次号查询")

        response = requests.get(f"{BASE_URL}/api/audit-logs", params={"batch_no": batch_no_1})
        logs = response.json()
        assert response.status_code == 200, "审计日志查询应成功"
        assert len(logs) >= 3, f"批次 {batch_no_1} 应有至少3条审计日志，实际: {len(logs)}"

        for log in logs:
            assert log["batch_no"] == batch_no_1, f"批次号应匹配: {log['batch_no']} != {batch_no_1}"

        print(f"✓ 按批次查询审计日志成功，共 {len(logs)} 条记录")

        # 步骤7: 重启服务验证数据持久性
        print_step(7, "重启服务验证 - 数据跨重启保留")

        # 记录重启前的关键数据（不调用会产生审计日志的接口）
        templates_before = requests.get(f"{BASE_URL}/api/templates").json()
        packages_before = requests.get(f"{BASE_URL}/api/task-packages").json()
        audit_before_count = len(requests.get(f"{BASE_URL}/api/audit-logs", params={"batch_no": batch_no_1}).json())

        # 验证重启前批次号可查询
        response = requests.get(f"{BASE_URL}/api/batch/batches/{batch_no_1}")
        assert response.status_code == 200, "重启前批次号查询失败"
        batch_before = response.json()
        assert batch_before["batch_no"] == batch_no_1, "重启前批次号不匹配"

        # 停止并重启服务
        if proc:
            stop_service(proc)
            proc = start_service()
        else:
            print("⚠️  外部服务，跳过重启测试")
            proc = None

        if proc:
            # 验证重启后的数据
            templates_after = requests.get(f"{BASE_URL}/api/templates").json()
            packages_after = requests.get(f"{BASE_URL}/api/task-packages").json()

            assert len(templates_after) == len(templates_before), f"重启后模板数量不一致: {len(templates_after)} != {len(templates_before)}"
            assert len(packages_after) == len(packages_before), f"重启后任务包数量不一致: {len(packages_after)} != {len(packages_before)}"

            # 验证批次号仍可查询
            response = requests.get(f"{BASE_URL}/api/batch/batches/{batch_no_1}")
            assert response.status_code == 200, "重启后批次号查询失败"
            batch_after = response.json()
            assert batch_after["batch_no"] == batch_no_1, "重启后批次号不匹配"
            assert batch_after["id"] == batch_before["id"], "重启后批次ID不匹配"

            # 验证导出数据包含批次号
            export_after = requests.get(f"{BASE_URL}/api/batch/export", params={"batch_no": batch_no_1}).json()
            assert export_after["export_count"] == 2, f"重启后导出数量应仍为2，实际: {export_after['export_count']}"
            for item in export_after["items"]:
                assert item["batch_no"] == batch_no_1, "重启后导出批次号不匹配"

            # 验证审计日志包含该批次（可能会有新增的导出日志，所以只验证至少有原来的数量）
            audit_after = requests.get(f"{BASE_URL}/api/audit-logs", params={"batch_no": batch_no_1}).json()
            assert len(audit_after) >= audit_before_count, f"重启后审计日志数量不应减少: {len(audit_after)} < {audit_before_count}"

            print("✓ 重启后模板和任务包数量一致")
            print("✓ 重启后批次号仍可查询")
            print("✓ 重启后导出数据包含正确批次号")
            print("✓ 重启后审计日志完整保留")

        # 步骤8: 连续5次导入验证极端情况
        print_step(8, "极端测试 - 同一秒内连续5次导入")

        batch_nos = []
        for i in range(5):
            import_data = {
                "templates": [
                    {
                        "name": f"极端测试-模板-{i+1}",
                        "description": f"极端测试模板{i+1}",
                        "check_items": [
                            {"device_code": f"EXT-DEV-{i+1}", "item_name": "测试项", "unit": "个", "standard_value": "≥0", "tolerance": "±0"}
                        ]
                    }
                ],
                "task_packages": [],
                "operator": "极端测试管理员"
            }
            response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data)
            data = response.json()
            assert response.status_code == 200, f"第{i+1}次导入请求失败"
            assert data["success"] == True, f"第{i+1}次导入应成功: {data.get('message')}"
            batch_nos.append(data["batch_no"])
            print(f"  第{i+1}次导入批次号: {data['batch_no']}")

        # 验证所有批次号都不同
        assert len(set(batch_nos)) == 5, f"5个批次号应有5个不同值，实际: {len(set(batch_nos))} 个不同"
        print("✓ 连续5次导入批次号全部唯一")

        # 验证所有批次号格式正确
        for i, bn in enumerate(batch_nos):
            assert bn.startswith("BATCH-"), f"第{i+1}个批次号格式错误: {bn}"
            parts = bn.split("-")
            assert len(parts) == 3, f"第{i+1}个批次号格式应为 BATCH-时间戳-序号: {bn}"
            assert len(parts[1]) == 17, f"第{i+1}个批次号时间戳应包含毫秒: {bn}"
            assert parts[2].isdigit(), f"第{i+1}个批次号序号应为数字: {bn}"
        print("✓ 所有批次号格式正确")

        print("\n" + "=" * 70)
        print("✅ 批次号唯一性回归测试全部通过！")
        print(f"   测试批次号: {batch_no_1}, {batch_no_2}")
        print("=" * 70)

        return True

    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if proc:
            stop_service(proc)


if __name__ == "__main__":
    success = test_batch_no_uniqueness()
    sys.exit(0 if success else 1)
