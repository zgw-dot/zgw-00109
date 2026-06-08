#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主链路测试脚本
测试流程：创建模板 → 生成任务包 → 发放 → 上传读数 → 解决冲突 → 同步 → 关闭 → 导出报告
"""

import requests
import json
from datetime import datetime, timedelta
import time

BASE_URL = "http://localhost:8000"
PKG_NO = f"PKG-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"


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


def test_main_flow():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    离线巡检任务包 - 主链路测试                 ║
╚══════════════════════════════════════════════════════════════╝
    """)

    template_id = None
    conflict_id = None

    try:
        print_step(1, "创建巡检模板")
        template_data = {
            "name": "变压器日常巡检模板-测试",
            "description": "用于测试的变压器巡检模板",
            "check_items": [
                {"device_code": "TRANS-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"},
                {"device_code": "TRANS-001", "item_name": "油位", "unit": "mm", "standard_value": "150-250", "tolerance": "±10"},
                {"device_code": "TRANS-002", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/templates", json=template_data)
        data = print_response(response)
        assert response.status_code == 201, "创建模板失败"
        template_id = data["id"]
        print(f"✓ 模板创建成功，ID: {template_id}")

        print_step(2, "生成任务包")
        package_data = {
            "package_no": PKG_NO,
            "template_id": template_id,
            "operator": "测试管理员"
        }
        response = requests.post(f"{BASE_URL}/api/task-packages", json=package_data)
        data = print_response(response)
        assert response.status_code == 201, "生成任务包失败"
        assert data["status"] == "draft", "任务包初始状态应为草稿"
        print(f"✓ 任务包创建成功，编号: {PKG_NO}，状态: {data['status']}")

        print_step(3, "发放任务包")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/issue?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 200, "发放任务包失败"
        assert data["old_status"] == "draft", "发放前状态应为草稿"
        assert data["new_status"] == "issued", "发放后状态应为已发放"
        print(f"✓ 任务包发放成功")

        print_step(4, "验证任务包状态")
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}")
        data = print_response(response)
        assert data["status"] == "issued", "任务包状态应为已发放"
        print(f"✓ 任务包状态验证通过")

        print_step(5, "上传第一批读数")
        collected_time1 = (datetime.now() - timedelta(hours=1)).isoformat()
        reading_data_1 = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "TRANS-001", "item_name": "油温", "reading_value": "78", "collected_at": collected_time1, "source_type": "offline"},
                {"device_code": "TRANS-001", "item_name": "油位", "reading_value": "180", "collected_at": collected_time1, "source_type": "offline"},
                {"device_code": "TRANS-002", "item_name": "油温", "reading_value": "72", "collected_at": collected_time1, "source_type": "offline"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_data_1)
        data = print_response(response)
        assert response.status_code == 200, "上传读数失败"
        assert data["readings_processed"] == 3, "应成功处理3条读数"
        assert data["conflicts_found"] == 0, "第一次上传不应有冲突"
        print(f"✓ 第一批读数上传成功，处理 {data['readings_processed']} 条，冲突 {data['conflicts_found']} 个")

        print_step(6, "上传第二批读数 - 制造冲突（同一设备同一检查项不同值）")
        collected_time2 = datetime.now().isoformat()
        reading_data_2 = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "TRANS-001", "item_name": "油温", "reading_value": "85", "collected_at": collected_time2, "source_type": "offline"},
                {"device_code": "TRANS-002", "item_name": "油温", "reading_value": "72", "collected_at": collected_time2, "source_type": "offline"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_data_2)
        data = print_response(response)
        assert response.status_code == 200, "上传读数失败"
        assert data["conflicts_found"] == 1, "应检测到1个冲突"
        assert data["readings_processed"] == 1, "应成功处理1条无冲突读数"
        conflict_id = data["conflicts"][0]["id"]
        print(f"✓ 冲突检测正常，冲突ID: {conflict_id}")

        print_step(7, "尝试直接标记为已同步（有未解决冲突，应失败）")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/sync?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 400, "有未解决冲突时同步应失败"
        assert "未解决的冲突" in data["detail"], "错误信息应包含未解决冲突"
        print(f"✓ 冲突拦截正常，无法直接同步")

        print_step(8, "尝试直接关闭任务包（当前状态是issued，应先检查状态流转）")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/close?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 400, "非synced状态关闭应失败"
        assert "不允许此操作" in data["detail"], "错误信息应说明状态不允许"
        print(f"✓ 状态流转检查正常，issued状态不能直接关闭")

        print_step(9, "解决冲突 - 保留新值")
        resolve_data = {
            "resolution_note": "现场核实，第二次读数更准确",
            "keep_value": "new",
            "resolved_by": "测试管理员"
        }
        response = requests.post(f"{BASE_URL}/api/conflicts/{conflict_id}/resolve", json=resolve_data)
        data = print_response(response)
        assert response.status_code == 200, "解决冲突失败"
        assert data["status"] == "resolved", "冲突状态应为已解决"
        print(f"✓ 冲突解决成功")

        print_step(10, "验证读数已更新为新值")
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        data = print_response(response)
        target_reading = next((r for r in data if r["device_code"] == "TRANS-001" and r["item_name"] == "油温"), None)
        assert target_reading is not None, "应找到对应的读数"
        assert target_reading["reading_value"] == "85", f"读数应更新为85，实际为{target_reading['reading_value']}"
        print(f"✓ 读数已更新为新值: 85")

        print_step(11, "标记任务包为已同步")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/sync?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 200, "标记同步失败"
        assert data["new_status"] == "synced", "状态应为已同步"
        print(f"✓ 任务包已标记为已同步")

        print_step(12, "synced状态下制造冲突，测试关闭时冲突拦截")
        conflict_reading = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "TRANS-002", "item_name": "油温", "reading_value": "90", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=conflict_reading)
        data = response.json()
        assert data["conflicts_found"] == 1, "应检测到新的冲突"
        print(f"  已制造新冲突，synced状态下有未解决冲突")

        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/close?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 400, "synced状态有未解决冲突时关闭应失败"
        assert "未解决的冲突" in data["detail"], "错误信息应包含未解决冲突"
        print(f"✓ synced状态冲突拦截正常，无法直接关闭")

        # 解决这个新冲突
        response = requests.get(f"{BASE_URL}/api/conflicts?package_no={PKG_NO}&status=open")
        open_conflicts = response.json()
        new_conflict = next(c for c in open_conflicts if c["device_code"] == "TRANS-002")
        resolve_data2 = {
            "resolution_note": "synced状态冲突，保留原值",
            "keep_value": "existing",
            "resolved_by": "测试管理员"
        }
        response = requests.post(f"{BASE_URL}/api/conflicts/{new_conflict['id']}/resolve", json=resolve_data2)
        assert response.status_code == 200, "解决冲突失败"
        print(f"✓ 新冲突已解决")

        print_step(13, "关闭任务包")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/close?operator=测试管理员")
        data = print_response(response)
        assert response.status_code == 200, "关闭任务包失败"
        assert data["new_status"] == "closed", "状态应为已关闭"
        print(f"✓ 任务包已关闭")

        print_step(14, "验证任务包最终状态")
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}")
        data = print_response(response)
        assert data["status"] == "closed", "任务包最终状态应为已关闭"
        print(f"✓ 任务包状态验证通过: {data['status']}")

        print_step(15, "导出 JSON 报告")
        response = requests.get(f"{BASE_URL}/api/reports/{PKG_NO}/json")
        assert response.status_code == 200, "导出JSON报告失败"
        report_data = response.json()
        print(f"报告摘要: {json.dumps(report_data['summary'], ensure_ascii=False, indent=2)}")
        assert report_data["package_info"]["status"] == "closed", "报告中状态应为已关闭"
        assert report_data["summary"]["total_readings"] >= 3, "报告中读数数量应正确"
        assert report_data["summary"]["resolved_conflicts"] == 2, "报告中应显示2个已解决冲突"
        print(f"✓ JSON 报告导出成功")

        with open(f"report_{PKG_NO}.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        print(f"  报告已保存为: report_{PKG_NO}.json")

        print_step(16, "导出 Excel 报告")
        response = requests.get(f"{BASE_URL}/api/reports/{PKG_NO}/excel")
        assert response.status_code == 200, "导出Excel报告失败"
        with open(f"report_{PKG_NO}.xlsx", "wb") as f:
            f.write(response.content)
        print(f"✓ Excel 报告导出成功，已保存为: report_{PKG_NO}.xlsx")

        print_step(17, "查看审计日志")
        response = requests.get(f"{BASE_URL}/api/audit-logs?entity_type=task_package")
        data = print_response(response, show_data=False)
        assert response.status_code == 200, "查询审计日志失败"
        logs = response.json()
        print(f"  相关审计日志数量: {len(logs)} 条")
        assert len(logs) > 0, "应有审计日志记录"
        print(f"✓ 审计日志记录正常")

        print("\n" + "="*60)
        print("✅ 主链路测试全部通过！")
        print(f"   测试任务包编号: {PKG_NO}")
        print("="*60)
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
    success = test_main_flow()
    exit(0 if success else 1)
