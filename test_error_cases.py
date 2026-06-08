#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异常场景测试脚本
测试内容：
1. 未知包编号上传
2. 同一设备重复提交不同读数（冲突检测）
3. 未解决冲突就关闭
4. 草稿状态上传读数（应失败）
5. 已关闭任务包上传读数（应失败）
6. 状态流转错误检测
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
PKG_NO = f"PKG-ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}"


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


def test_error_cases():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                  离线巡检任务包 - 异常场景测试                 ║
╚══════════════════════════════════════════════════════════════╝
    """)

    template_id = None
    passed_tests = 0
    total_tests = 0

    try:
        # 先创建基础数据
        print_step("预备", "创建测试用模板和任务包")
        
        template_data = {
            "name": "异常测试模板",
            "description": "用于异常场景测试的模板",
            "check_items": [
                {"device_code": "DEV-ERR-001", "item_name": "温度", "unit": "°C"},
                {"device_code": "DEV-ERR-002", "item_name": "压力", "unit": "MPa"}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/templates", json=template_data)
        assert response.status_code == 201, "创建模板失败"
        template_id = response.json()["id"]
        print(f"✓ 模板创建成功，ID: {template_id}")

        # 测试1: 未知包编号上传
        total_tests += 1
        print_step(1, "测试: 未知包编号上传（应返回404错误）")
        unknown_reading = {
            "package_no": "UNKNOWN-PKG-9999",
            "readings": [
                {"device_code": "DEV-001", "item_name": "温度", "reading_value": "25", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=unknown_reading)
        data = print_response(response)
        assert response.status_code == 404, "未知包编号应返回404"
        assert "不存在" in data["detail"], "错误信息应包含'不存在'"
        print("✓ 测试通过: 未知包编号正确返回404错误")
        passed_tests += 1

        # 测试2: 草稿状态上传读数
        total_tests += 1
        print_step(2, "测试: 草稿状态上传读数（应失败，需先发放）")
        
        # 创建任务包（草稿状态）
        package_data = {
            "package_no": PKG_NO,
            "template_id": template_id,
            "operator": "测试员"
        }
        response = requests.post(f"{BASE_URL}/api/task-packages", json=package_data)
        assert response.status_code == 201, "创建任务包失败"
        
        draft_reading = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-ERR-001", "item_name": "温度", "reading_value": "30", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=draft_reading)
        data = print_response(response)
        assert response.status_code == 400, "草稿状态上传读数应返回400"
        assert "不允许" in data["detail"], "错误信息应包含'不允许'"
        print("✓ 测试通过: 草稿状态无法上传读数")
        passed_tests += 1

        # 发放任务包
        print_step("预备", "发放任务包以便后续测试")
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/issue")
        assert response.status_code == 200, "发放任务包失败"
        print("✓ 任务包已发放")

        # 测试3: 同一设备重复提交不同读数（冲突检测）
        total_tests += 1
        print_step(3, "测试: 同一设备重复提交不同读数（应检测到冲突，不覆盖原值）")
        
        # 第一次上传
        collected_time1 = datetime.now().isoformat()
        reading_1 = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-ERR-001", "item_name": "温度", "reading_value": "25", "collected_at": collected_time1}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_1)
        data = print_response(response)
        assert response.status_code == 200, "第一次上传应成功"
        assert data["conflicts_found"] == 0, "第一次上传不应有冲突"
        print("  第一次上传成功，读数: 25")

        # 验证原始值
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        readings_before = response.json()
        original_value = next(r["reading_value"] for r in readings_before 
                            if r["device_code"] == "DEV-ERR-001" and r["item_name"] == "温度")
        assert original_value == "25", "原始值应为25"
        print(f"  数据库当前值: {original_value}")

        # 第二次上传（不同值）
        collected_time2 = datetime.now().isoformat()
        reading_2 = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-ERR-001", "item_name": "温度", "reading_value": "35", "collected_at": collected_time2}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=reading_2)
        data = print_response(response)
        assert response.status_code == 200, "第二次上传应返回成功（带冲突）"
        assert data["conflicts_found"] == 1, "应检测到1个冲突"
        assert data["readings_processed"] == 0, "不应处理任何读数"
        print("  第二次上传（值35）检测到冲突")

        # 验证原值未被覆盖（数据不污染）
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        readings_after = response.json()
        current_value = next(r["reading_value"] for r in readings_after 
                           if r["device_code"] == "DEV-ERR-001" and r["item_name"] == "温度")
        assert current_value == "25", f"原值应保持25，不应被覆盖，实际为{current_value}"
        print(f"✓ 测试通过: 原值保持为 {current_value}，未被污染")
        passed_tests += 1

        # 验证冲突记录已创建
        response = requests.get(f"{BASE_URL}/api/conflicts?package_no={PKG_NO}&status=open")
        conflicts = response.json()
        assert len(conflicts) >= 1, "应存在未解决的冲突"
        conflict = conflicts[0]
        assert conflict["existing_value"] == "25", "冲突记录中原有值应正确"
        assert conflict["new_value"] == "35", "冲突记录中新值应正确"
        print(f"✓ 测试通过: 冲突记录已创建，{conflict['existing_value']} vs {conflict['new_value']}")
        passed_tests += 1

        # 测试4: 未解决冲突就关闭
        total_tests += 1
        print_step(4, "测试: 未解决冲突就同步/关闭（应失败）")
        
        # 尝试同步（有未解决冲突）
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/sync")
        data = print_response(response)
        assert response.status_code == 400, "有冲突时同步应失败"
        assert "未解决的冲突" in data["detail"], "错误信息应包含'未解决的冲突'"
        print("✓ 测试通过: 未解决冲突时无法同步")
        passed_tests += 1

        # 先同步需要先解决冲突，这里测试关闭同样会因为状态不对而失败
        # 先确认状态是issued，关闭需要synced状态
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}")
        status = response.json()["status"]
        print(f"  当前任务包状态: {status}")
        
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/close")
        data = print_response(response)
        # 这里会因为状态不对而失败（issued不能直接close，需要先sync）
        assert response.status_code == 400, "非synced状态关闭应失败"
        assert "不允许此操作" in data["detail"], "错误信息应说明不允许"
        print("✓ 测试通过: 状态不正确时无法关闭")
        passed_tests += 1

        # 测试5: 解决冲突后验证数据可以更新
        total_tests += 1
        print_step(5, "测试: 解决冲突（保留新值）后验证数据更新")
        
        conflict_id = conflict["id"]
        resolve_data = {
            "resolution_note": "测试保留新值",
            "keep_value": "new",
            "resolved_by": "测试员"
        }
        response = requests.post(f"{BASE_URL}/api/conflicts/{conflict_id}/resolve", json=resolve_data)
        data = print_response(response)
        assert response.status_code == 200, "解决冲突应成功"
        assert data["status"] == "resolved", "冲突状态应为已解决"
        
        # 验证读数已更新
        response = requests.get(f"{BASE_URL}/api/task-packages/{PKG_NO}/readings")
        readings_final = response.json()
        final_value = next(r["reading_value"] for r in readings_final 
                         if r["device_code"] == "DEV-ERR-001" and r["item_name"] == "温度")
        assert final_value == "35", f"解决冲突后值应更新为35，实际为{final_value}"
        print(f"✓ 测试通过: 冲突解决后读数已更新为 {final_value}")
        passed_tests += 1

        # 测试6: 已关闭任务包上传读数
        total_tests += 1
        print_step(6, "测试: 同步并关闭任务包后上传读数（应失败）")
        
        # 同步
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/sync")
        assert response.status_code == 200, "同步应成功"
        
        # 关闭
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/close")
        assert response.status_code == 200, "关闭应成功"
        
        # 尝试上传读数到已关闭的任务包
        closed_reading = {
            "package_no": PKG_NO,
            "readings": [
                {"device_code": "DEV-ERR-002", "item_name": "压力", "reading_value": "1.5", "collected_at": datetime.now().isoformat()}
            ]
        }
        response = requests.post(f"{BASE_URL}/api/readings/upload", json=closed_reading)
        data = print_response(response)
        assert response.status_code == 400, "已关闭任务包上传读数应失败"
        assert "不允许" in data["detail"], "错误信息应包含'不允许'"
        print("✓ 测试通过: 已关闭任务包无法上传读数")
        passed_tests += 1

        # 测试7: 状态流转错误
        total_tests += 1
        print_step(7, "测试: 状态流转错误检测（已关闭不能再发放）")
        
        response = requests.post(f"{BASE_URL}/api/task-packages/{PKG_NO}/issue")
        data = print_response(response)
        assert response.status_code == 400, "已关闭任务包不能再发放"
        assert "不允许此操作" in data["detail"], "错误信息应说明不允许"
        print("✓ 测试通过: 状态流转规则正确执行")
        passed_tests += 1

        # 测试8: 重复编号的任务包
        total_tests += 1
        print_step(8, "测试: 创建重复编号的任务包（应失败）")
        
        duplicate_package = {
            "package_no": PKG_NO,  # 使用已存在的编号
            "template_id": template_id,
            "operator": "测试员"
        }
        response = requests.post(f"{BASE_URL}/api/task-packages", json=duplicate_package)
        data = print_response(response)
        assert response.status_code == 400, "重复编号应返回400"
        assert "已存在" in data["detail"], "错误信息应包含'已存在'"
        print("✓ 测试通过: 任务包编号唯一性校验正常")
        passed_tests += 1

        # 测试9: 删除已关联任务包的模板
        total_tests += 1
        print_step(9, "测试: 删除已关联任务包的模板（应失败）")
        
        response = requests.delete(f"{BASE_URL}/api/templates/{template_id}")
        data = print_response(response)
        assert response.status_code == 400, "已关联任务包的模板不能删除"
        assert "无法删除" in data["detail"], "错误信息应包含'无法删除'"
        print("✓ 测试通过: 模板删除保护机制正常")
        passed_tests += 1

        print("\n" + "="*60)
        print(f"✅ 异常场景测试完成: {passed_tests}/{total_tests} 测试通过")
        if passed_tests == total_tests:
            print("   所有异常场景测试通过！")
        else:
            print(f"   ❗ 有 {total_tests - passed_tests} 个测试未通过")
        print("="*60)
        return passed_tests == total_tests

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
    success = test_error_cases()
    exit(0 if success else 1)
