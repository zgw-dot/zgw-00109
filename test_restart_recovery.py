#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
重启恢复测试脚本
测试内容：
1. 创建数据并上传读数
2. 制造并解决冲突
3. 验证数据持久化到数据库
4. 模拟重启后验证数据完整性
5. 重启后导出报告验证
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
PKG_NO = f"PKG-RESTORE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
SNAPSHOT_FILE = f"snapshot_{PKG_NO}.json"


def print_step(step_no, description):
    print(f"\n{'='*60}")
    print(f"步骤 {step_no}: {description}")
    print(f"{'='*60}")


def print_response(response, show_data=True):
    print(f"状态码: {response.status_code}")
    if show_data and response.content:
        try:
            data = response.json()
            print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
            return data
        except:
            print(f"响应: {response.text}")
    return None


def save_snapshot(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"  数据快照已保存到: {SNAPSHOT_FILE}")


def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def test_restart_recovery():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                 离线巡检任务包 - 重启恢复测试                  ║
╚══════════════════════════════════════════════════════════════╝
    """)

    template_id = None
    conflict_id = None

    try:
        # Phase 1: 创建测试数据
        print_step(1, "第一阶段: 创建测试数据（模拟重启前）")
        
        # 创建模板
        template_data = {
            "name": "重启恢复测试模板",
            "description": "用于测试重启后数据恢复的模板",
            "check_items": [
                {"device_code": "DEV-RESTORE-001", "item_name": "温度", "unit": "°C", "standard_value": "20-30"},
                {"device_code": "DEV-RESTORE-001", "item_name": "湿度", "unit": "%RH", "standard_value": "40-60"},
                {"device_code": "DEV-RESTORE-002", "item_name": "温度", "unit": "°C", "standard_value": "20-30"},
                {"device_code": "DEV-RESTORE-002", "item_name": "压力", "unit": "MPa", "standard_value": "0.5-1.5"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/templates", json=template_data)
        assert response.status_code == 201, "创建模板失败"
        template_id = response.json()["id"]
        print(f"✓ 模板创建成功，ID: {template_id}")

        # 创建任务包
        package_data = {
            "package_no": PKG_NO,
            "template_id": template_id,
            "operator": "恢复测试员"
        }
        response = requests.post(f"{BASE_URL}/api/task-packages", json=package_data)
        assert response.status_code == 201, "创建任务包失败"
        print(f"✓ 任务包创建成功，编号: {PKG_NO}")

        # 发放任务包
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/issue?operator=恢复测试员")
        assert response.status_code == 200, "发放任务包失败"
        print("✓ 任务包已发放")

        # 上传第一批读数
        collected_time = (datetime.now() - timedelta(hours=2)).isoformat()
        reading_data = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-RESTORE-001", "item_name": "温度", "reading_value": "25", "collected_at": collected_time},
                {"device_code": "DEV-RESTORE-001", "item_name": "湿度", "reading_value": "50", "collected_at": collected_time},
                {"device_code": "DEV-RESTORE-002", "item_name": "温度", "reading_value": "27", "collected_at": collected_time},
                {"device_code": "DEV-RESTORE-002", "item_name": "压力", "reading_value": "1.0", "collected_at": collected_time}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_data)
        data = print_response(response)
        assert response.status_code == 200, "上传读数失败"
        assert data["readings_processed"] == 4, "应成功处理4条读数"
        print("✓ 第一批读数上传成功（4条）")

        # 制造冲突并解决
        print_step(2, "制造并解决冲突，验证冲突状态持久化")
        
        conflict_reading = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-RESTORE-001", "item_name": "温度", "reading_value": "28", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=conflict_reading)
        data = response.json()
        assert data["conflicts_found"] == 1, "应检测到冲突"
        conflict_id = data["conflicts"][0]["id"]
        print(f"✓ 冲突已创建，ID: {conflict_id}")

        # 解决冲突 - 保留新值
        resolve_data = {
            "resolution_note": "重启测试-保留新值",
            "keep_value": "new",
            "resolved_by": "恢复测试员"
        }
        response = requests.post(f"{BASE_URL}/api/conflicts/{conflict_id}/resolve", json=resolve_data)
        assert response.status_code == 200, "解决冲突失败"
        assert response.json()["status"] == "resolved"
        print("✓ 冲突已解决")

        # 再上传一个不解决的冲突，验证未解决的冲突也能持久化
        conflict_reading2 = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-RESTORE-002", "item_name": "温度", "reading_value": "30", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=conflict_reading2)
        data = response.json()
        assert data["conflicts_found"] == 1, "应检测到第二个冲突"
        open_conflict_id = data["conflicts"][0]["id"]
        print(f"✓ 未解决冲突已创建，ID: {open_conflict_id}（保持未解决状态）")

        # 保存数据快照
        print_step(3, "保存当前数据快照")
        
        # 获取当前状态
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}")
        package_info = response.json()
        
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        readings = response.json()
        
        response = requests.get(f"{BASE_URL}/api/conflicts?package_no={PKG_NO}")
        conflicts = response.json()
        
        response = requests.get(f"{BASE_URL}/api/audit-logs?entity_type=task_package&entity_id={package_info['id']}")
        audit_logs = response.json()

        snapshot = {
            "package_no": PKG_NO,
            "snapshot_time": datetime.now().isoformat(),
            "package_info": package_info,
            "readings": readings,
            "readings_count": len(readings),
            "conflicts": conflicts,
            "conflicts_count": len(conflicts),
            "open_conflicts_count": len([c for c in conflicts if c["status"] == "open"]),
            "resolved_conflicts_count": len([c for c in conflicts if c["status"] == "resolved"]),
            "audit_logs_count": len(audit_logs),
            "expected_values": {
                "DEV-RESTORE-001-温度": "28",  # 解决冲突后的值
                "DEV-RESTORE-001-湿度": "50",
                "DEV-RESTORE-002-温度": "27",  # 未解决冲突，应保持原值
                "DEV-RESTORE-002-压力": "1.0"
            }
        }
        save_snapshot(snapshot)

        print("\n" + "="*60)
        print("📋 重启前数据摘要:")
        print(f"  任务包状态: {snapshot['package_info']['status']}")
        print(f"  读数数量: {snapshot['readings_count']}")
        print(f"  冲突总数: {snapshot['conflicts_count']}")
        print(f"    - 已解决: {snapshot['resolved_conflicts_count']}")
        print(f"    - 未解决: {snapshot['open_conflicts_count']}")
        print(f"  审计日志数量: {snapshot['audit_logs_count']}")
        print("="*60)

        # Phase 2: 模拟重启后验证
        print_step(4, "第二阶段: 验证数据持久化（模拟重启后）")
        
        print("\n⚠️  请按以下步骤操作:")
        print("  1. 停止当前服务 (Ctrl+C)")
        print("  2. 重新启动服务: python main.py")
        print("  3. 等待服务启动后，按回车键继续验证...")
        
        try:
            input("\n按回车键继续...")
        except:
            pass

        print("\n正在验证重启后的数据...")

        # 验证任务包存在且状态正确
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}")
        assert response.status_code == 200, f"重启后找不到任务包 {PKG_NO}"
        restored_package = response.json()
        assert restored_package["status"] == snapshot["package_info"]["status"], \
            f"任务包状态不匹配: 期望 {snapshot['package_info']['status']}, 实际 {restored_package['status']}"
        print(f"✓ 任务包存在，状态正确: {restored_package['status']}")

        # 验证读数数量和值
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        restored_readings = response.json()
        assert len(restored_readings) == snapshot["readings_count"], \
            f"读数数量不匹配: 期望 {snapshot['readings_count']}, 实际 {len(restored_readings)}"
        print(f"✓ 读数数量正确: {len(restored_readings)} 条")

        # 验证每个读数值
        for key, expected_value in snapshot["expected_values"].items():
            device_code, item_name = key.split("-", 1)
            item_name = "-".join(key.split("-")[1:])
            reading = next((r for r in restored_readings 
                          if r["device_code"] == device_code and r["item_name"] == item_name), None)
            assert reading is not None, f"找不到读数: {key}"
            assert reading["reading_value"] == expected_value, \
                f"读数值不匹配 {key}: 期望 {expected_value}, 实际 {reading['reading_value']}"
            print(f"  ✓ {key}: {reading['reading_value']} (正确)")

        # 验证冲突状态
        response = requests.get(f"{BASE_URL}/api/conflicts?package_no={PKG_NO}")
        restored_conflicts = response.json()
        assert len(restored_conflicts) == snapshot["conflicts_count"], \
            f"冲突数量不匹配: 期望 {snapshot['conflicts_count']}, 实际 {len(restored_conflicts)}"
        
        open_count = len([c for c in restored_conflicts if c["status"] == "open"])
        resolved_count = len([c for c in restored_conflicts if c["status"] == "resolved"])
        assert open_count == snapshot["open_conflicts_count"], \
            f"未解决冲突数量不匹配: 期望 {snapshot['open_conflicts_count']}, 实际 {open_count}"
        assert resolved_count == snapshot["resolved_conflicts_count"], \
            f"已解决冲突数量不匹配: 期望 {snapshot['resolved_conflicts_count']}, 实际 {resolved_count}"
        print(f"✓ 冲突状态正确: 未解决 {open_count} 个, 已解决 {resolved_count} 个")

        # 验证审计日志存在
        response = requests.get(f"{BASE_URL}/api/audit-logs?entity_type=task_package&entity_id={restored_package['id']}")
        restored_logs = response.json()
        assert len(restored_logs) >= snapshot["audit_logs_count"], \
            f"审计日志数量不足: 期望至少 {snapshot['audit_logs_count']}, 实际 {len(restored_logs)}"
        print(f"✓ 审计日志存在: {len(restored_logs)} 条")

        # Phase 3: 重启后导出报告
        print_step(5, "第三阶段: 重启后导出报告验证")
        
        # 导出 JSON 报告
        response = requests.get(f"{BASE_URL}/api/reports/{PKG_NO}/json")
        assert response.status_code == 200, "导出JSON报告失败"
        report = response.json()
        
        print("报告摘要:")
        print(f"  任务包状态: {report['package_info']['status']}")
        print(f"  读数总数: {report['summary']['total_readings']}")
        print(f"  冲突总数: {report['summary']['total_conflicts']}")
        print(f"  未解决冲突: {report['summary']['open_conflicts']}")
        print(f"  已解决冲突: {report['summary']['resolved_conflicts']}")
        
        assert report["package_info"]["status"] == restored_package["status"], "报告中状态不正确"
        assert report["summary"]["total_readings"] == snapshot["readings_count"], "报告中读数数量不正确"
        assert report["summary"]["total_conflicts"] == snapshot["conflicts_count"], "报告中冲突数量不正确"
        assert report["summary"]["open_conflicts"] == snapshot["open_conflicts_count"], "报告中未解决冲突数量不正确"
        assert report["summary"]["resolved_conflicts"] == snapshot["resolved_conflicts_count"], "报告中已解决冲突数量不正确"
        
        # 验证报告中的读数值
        for key, expected_value in snapshot["expected_values"].items():
            device_code, item_name = key.split("-", 1)
            item_name = "-".join(key.split("-")[1:])
            reading = next((r for r in report["readings"] 
                          if r["device_code"] == device_code and r["item_name"] == item_name), None)
            assert reading is not None, f"报告中找不到读数: {key}"
            assert reading["reading_value"] == expected_value, \
                f"报告中读数值不匹配 {key}: 期望 {expected_value}, 实际 {reading['reading_value']}"
        
        print("✓ JSON 报告数据完整且正确")

        # 导出 Excel 报告
        response = requests.get(f"{BASE_URL}/api/reports/{PKG_NO}/excel")
        assert response.status_code == 200, "导出Excel报告失败"
        excel_filename = f"restart_report_{PKG_NO}.xlsx"
        with open(excel_filename, "wb") as f:
            f.write(response.content)
        print(f"✓ Excel 报告导出成功，已保存为: {excel_filename}")

        # 验证数据库文件存在
        db_path = os.path.join(os.path.dirname(__file__), "inspection.db")
        assert os.path.exists(db_path), "数据库文件不存在"
        db_size = os.path.getsize(db_path)
        print(f"✓ 数据库文件存在，大小: {db_size} bytes")

        print("\n" + "="*60)
        print("✅ 重启恢复测试全部通过！")
        print(f"   测试任务包: {PKG_NO}")
        print(f"   数据快照: {SNAPSHOT_FILE}")
        print(f"   已验证: 任务包状态 ✓ 读数 ✓ 冲突状态 ✓ 审计日志 ✓ 报告导出 ✓")
        print("="*60)

        # 清理快照文件
        if os.path.exists(SNAPSHOT_FILE):
            os.remove(SNAPSHOT_FILE)

        return True

    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务，请先启动服务: python main.py")
        return False
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_restart_recovery()
    exit(0 if success else 1)
