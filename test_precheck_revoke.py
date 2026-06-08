#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量导入预检和撤销功能回归测试
测试场景：
1. 导入前预检（JSON/CSV）- 只校验不入库
2. 正常导入后撤销
3. 已发放或有冲突时拒绝撤销
4. 重复撤销返回清楚错误
5. 重启后批次状态、撤销结果、导出过滤保持一致
6. 操作人贯穿所有接口
"""

import requests
import json
import time
import subprocess
import sys
import os
import signal
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"
TEST_TIMESTAMP = datetime.now().strftime('%Y%m%d%H%M%S')


def print_step(step_no, title):
    print(f"\n{'=' * 70}")
    print(f"步骤 {step_no}: {title}")
    print(f"{'=' * 70}")


def print_response(response, show_data=True, max_len=1200):
    print(f"状态码: {response.status_code}")
    if show_data and response.content:
        try:
            data = response.json()
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(data_str) > max_len:
                data_str = data_str[:max_len] + "...(已截断)"
            print(f"响应: {data_str}")
            return data
        except:
            print(f"响应: {response.text[:500]}")
    return None


def wait_for_service(timeout=30):
    """等待服务启动"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2)
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


def test_precheck_and_revoke():
    print("\n" + "╔" + "═" * 70 + "╗")
    print("║" + " " * 10 + "批量导入预检和撤销功能回归测试" + " " * 28 + "║")
    print("╚" + "═" * 70 + "╝")

    service_running = False
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code == 200:
            service_running = True
            print("✓ 服务已在运行")
    except:
        pass

    proc = None
    if not service_running:
        proc = start_service()

    template_ids = {}
    batch_no_import = None
    batch_no_precheck_json = None
    batch_no_precheck_csv = None
    batch_no_revoke_test = None

    try:
        # ========== 测试1: JSON预检 - 不落库 ==========
        print_step(1, "JSON预检 - 校验不入库")

        # 记录预检前的数量
        templates_before = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_before = len(requests.get(f"{BASE_URL}/api/task-packages").json())
        print(f"  预检前: 模板 {templates_before} 个, 任务包 {packages_before} 个")

        precheck_json_data = {
            "templates": [
                {
                    "name": f"预检测试-变压器-V1-{TEST_TIMESTAMP}",
                    "description": "JSON预检测试模板",
                    "check_items": [
                        {"device_code": "DEV-JSON-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"},
                        {"device_code": "DEV-JSON-001", "item_name": "油位", "unit": "mm", "standard_value": "150-250", "tolerance": "±10"}
                    ]
                },
                {
                    "name": f"预检测试-开关柜-V1-{TEST_TIMESTAMP}",
                    "description": "JSON预检测试模板2",
                    "check_items": [
                        {"device_code": "DEV-JSON-002", "item_name": "温度", "unit": "°C", "standard_value": "≤65", "tolerance": "±3"}
                    ]
                }
            ],
            "task_packages": [
                {
                    "package_no": f"PKG-JSON-PRE-{TEST_TIMESTAMP}",
                    "template_id": 99999,
                    "operator": "测试管理员-JSON预检"
                }
            ],
            "operator": "测试管理员-JSON预检"
        }

        response = requests.post(f"{BASE_URL}/api/batch/precheck/json", json=precheck_json_data)
        data = print_response(response)

        assert response.status_code == 200, "JSON预检请求应成功"
        assert data["success"] == False, "存在模板不存在的任务包，预检应失败"
        assert data["total_records"] == 3, f"应检测3条记录，实际: {data['total_records']}"
        assert data["will_add"] == 2, f"应新增2条模板，实际: {data['will_add']}"
        assert data["will_duplicate"] == 0, f"应无重复，实际: {data['will_duplicate']}"
        assert data["missing_fields"] == 0, f"应无字段缺失，实际: {data['missing_fields']}"
        assert data["template_not_found"] == 1, f"应检测1个模板不存在，实际: {data['template_not_found']}"
        assert "batch_no" in data, "预检应返回批次号"
        batch_no_precheck_json = data["batch_no"]

        # 验证预检不落库
        templates_after = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_after = len(requests.get(f"{BASE_URL}/api/task-packages").json())
        assert templates_after == templates_before, f"预检不应新增模板，前: {templates_before}, 后: {templates_after}"
        assert packages_after == packages_before, f"预检不应新增任务包，前: {packages_before}, 后: {packages_after}"
        print("✓ JSON预检通过，数据未入库")

        # 验证预检审计日志
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "batch_no": batch_no_precheck_json,
            "action": "batch_precheck"
        })
        logs = response.json()
        assert len(logs) >= 1, f"预检应有审计日志，实际: {len(logs)}"
        assert logs[0]["operator"] == "测试管理员-JSON预检", "操作人应正确记录"
        print("✓ JSON预检审计日志正确记录")

        # ========== 测试2: CSV预检 - 校验不入库 ==========
        print_step(2, "CSV预检 - 校验不入库")

        templates_before = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_before = len(requests.get(f"{BASE_URL}/api/task-packages").json())

        csv_file = open("test_precheck_revoke.csv", "rb")
        response = requests.post(
            f"{BASE_URL}/api/batch/precheck/csv",
            files={"file": ("test_precheck_revoke.csv", csv_file, "text/csv")},
            params={"operator": "测试管理员-CSV预检"}
        )
        data = print_response(response)
        csv_file.close()

        assert response.status_code == 200, "CSV预检请求应成功"
        assert data["success"] == False, "存在模板不存在的任务包，预检应失败"
        assert data["total_records"] == 4, f"应检测4条记录，实际: {data['total_records']}"
        assert data["will_add"] == 2, f"应新增2条模板，实际: {data['will_add']}"
        assert data["template_not_found"] == 2, f"应检测2个模板不存在，实际: {data['template_not_found']}"
        batch_no_precheck_csv = data["batch_no"]

        # 验证预检不落库
        templates_after = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_after = len(requests.get(f"{BASE_URL}/api/task-packages").json())
        assert templates_after == templates_before, "CSV预检不应新增模板"
        assert packages_after == packages_before, "CSV预检不应新增任务包"
        print("✓ CSV预检通过，数据未入库")

        # ========== 测试3: 正常导入后撤销 ==========
        print_step(3, "正常导入后撤销 - 草稿状态可撤销")

        # 先导入模板
        import_data = {
            "templates": [
                {
                    "name": f"撤销测试-变压器-V1-{TEST_TIMESTAMP}",
                    "description": "撤销测试模板",
                    "check_items": [
                        {"device_code": "DEV-REV-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                }
            ],
            "task_packages": [],
            "operator": "测试管理员-撤销"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data)
        data = print_response(response)
        assert data["success"] == True, "模板导入应成功"

        # 获取模板ID
        for result in data["results"]:
            if result["success"] and result["record_type"] == "template":
                template_ids["撤销测试-变压器"] = int(result["message"].split("ID: ")[1])

        # 导入任务包（草稿状态）
        import_data2 = {
            "templates": [],
            "task_packages": [
                {
                    "package_no": f"PKG-REVOKE-{TEST_TIMESTAMP}",
                    "template_id": template_ids["撤销测试-变压器"],
                    "operator": "测试管理员-撤销"
                }
            ],
            "operator": "测试管理员-撤销"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data2)
        data = print_response(response)
        assert data["success"] == True, "任务包导入应成功"
        batch_no_revoke_test = data["batch_no"]
        print(f"  导入批次号: {batch_no_revoke_test}")

        # 撤销前校验
        response = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no_revoke_test}")
        data = print_response(response)
        assert response.status_code == 200, "撤销前校验请求应成功"
        assert data["allowed"] == True, "草稿状态应允许撤销"
        assert data["templates_count"] == 0, f"该批次应无模板，实际: {data['templates_count']}"
        assert data["packages_count"] == 1, f"该批次应有1个任务包，实际: {data['packages_count']}"
        assert data["issued_packages"] == 0, "应无已发放任务包"
        assert data["synced_packages"] == 0, "应无已同步任务包"
        assert data["open_conflicts"] == 0, "应无未解决冲突"
        assert data["is_revoked"] == False, "批次尚未撤销"
        print("✓ 撤销前校验通过，允许撤销")

        # 记录撤销前数量
        templates_before = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_before = len(requests.get(f"{BASE_URL}/api/task-packages").json())

        # 执行撤销
        revoke_data = {"reason": "测试撤销功能，数据有误"}
        response = requests.post(
            f"{BASE_URL}/api/batch/revoke/batch/{batch_no_revoke_test}",
            json=revoke_data,
            params={"operator": "测试管理员-撤销"}
        )
        data = print_response(response)

        assert response.status_code == 200, "撤销请求应成功"
        assert data["success"] == True, "撤销应成功"
        assert data["revoked_packages"] == 1, f"应撤销1个任务包，实际: {data['revoked_packages']}"
        assert data["operator"] == "测试管理员-撤销", "操作人应正确记录"
        print("✓ 撤销成功")

        # 验证数据已删除
        templates_after = len(requests.get(f"{BASE_URL}/api/templates").json())
        packages_after = len(requests.get(f"{BASE_URL}/api/task-packages").json())
        assert packages_after == packages_before - 1, f"任务包应减少1个，前: {packages_before}, 后: {packages_after}"
        assert templates_after == templates_before, "模板数量应不变"
        print("✓ 撤销后数据已删除")

        # 验证批次状态已更新
        response = requests.get(f"{BASE_URL}/api/batch/batches/{batch_no_revoke_test}")
        data = response.json()
        assert data["is_revoked"] == 1, "批次应标记为已撤销"
        assert data["revoked_by"] == "测试管理员-撤销", "撤销人应正确记录"
        assert data["revocation_reason"] == "测试撤销功能，数据有误", "撤销原因应正确记录"
        assert data["status"] == "revoked", "批次状态应为revoked"
        print("✓ 批次状态已更新为已撤销")

        # 验证撤销审计日志
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "batch_no": batch_no_revoke_test,
            "action": "batch_revoke"
        })
        logs = response.json()
        assert len(logs) >= 1, "撤销应有审计日志"
        assert logs[0]["operator"] == "测试管理员-撤销", "操作人应正确记录"
        print("✓ 撤销审计日志正确记录")

        # ========== 测试4: 重复撤销返回清楚错误 ==========
        print_step(4, "重复撤销 - 返回清楚错误")

        response = requests.post(
            f"{BASE_URL}/api/batch/revoke/batch/{batch_no_revoke_test}",
            json={"reason": "重复撤销测试"},
            params={"operator": "测试管理员-重复撤销"}
        )
        data = print_response(response)

        assert response.status_code == 400, "重复撤销应返回400错误"
        assert "已被撤销" in data["detail"], "错误信息应明确说明已撤销"
        assert "撤销时间" in data["detail"], "错误信息应包含撤销时间"
        assert "撤销人" in data["detail"], "错误信息应包含撤销人"
        print("✓ 重复撤销检测正常，错误信息清晰")

        # 验证撤销前校验也能正确识别已撤销
        response = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no_revoke_test}")
        data = response.json()
        assert data["allowed"] == False, "已撤销批次校验应不通过"
        assert data["is_revoked"] == True, "应正确识别已撤销状态"
        assert "已被撤销" in data["blocking_issues"][0], "阻塞原因应说明已撤销"
        print("✓ 撤销前校验正确识别已撤销状态")

        # ========== 测试5: 已发放时拒绝撤销 ==========
        print_step(5, "已发放状态 - 拒绝撤销")

        # 先导入并发放
        import_data3 = {
            "templates": [
                {
                    "name": f"发放测试-变压器-V1-{TEST_TIMESTAMP}",
                    "description": "发放撤销测试模板",
                    "check_items": [
                        {"device_code": "DEV-ISSUE-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                }
            ],
            "task_packages": [],
            "operator": "测试管理员-发放"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data3)
        data = response.json()
        assert data["success"] == True

        for result in data["results"]:
            if result["success"] and result["record_type"] == "template":
                template_ids["发放测试-变压器"] = int(result["message"].split("ID: ")[1])

        import_data4 = {
            "templates": [],
            "task_packages": [
                {
                    "package_no": f"PKG-ISSUE-{TEST_TIMESTAMP}",
                    "template_id": template_ids["发放测试-变压器"],
                    "operator": "测试管理员-发放"
                }
            ],
            "operator": "测试管理员-发放"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data4)
        data = response.json()
        batch_no_issue_test = data["batch_no"]

        # 发放任务包
        response = requests.post(
            f"{BASE_URL}/api/batch/publish/PKG-ISSUE-{TEST_TIMESTAMP}",
            params={"operator": "测试管理员-发放"}
        )
        assert response.status_code == 200, "发放应成功"
        print(f"  任务包已发放")

        # 校验撤销 - 应拒绝
        response = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no_issue_test}")
        data = print_response(response)
        assert data["allowed"] == False, "已发放批次应不允许撤销"
        assert data["issued_packages"] == 1, "应检测到1个已发放任务包"
        assert "已发放" in data["blocking_issues"][0], "阻塞原因应说明已发放"
        print("✓ 已发放状态撤销拦截正常")

        # 尝试撤销 - 应失败
        response = requests.post(
            f"{BASE_URL}/api/batch/revoke/batch/{batch_no_issue_test}",
            json={"reason": "测试已发放撤销"},
            params={"operator": "测试管理员-发放"}
        )
        assert response.status_code == 400, "已发放批次撤销应失败"
        assert "已发放" in response.json()["detail"], "错误信息应说明已发放"
        print("✓ 已发放批次撤销请求被正确拒绝")

        # ========== 测试6: 有未解决冲突时拒绝撤销 ==========
        print_step(6, "有未解决冲突 - 拒绝撤销")

        # 先创建新批次，导入并发放，上传读数制造冲突
        import_data5 = {
            "templates": [
                {
                    "name": f"冲突测试-变压器-V1-{TEST_TIMESTAMP}",
                    "description": "冲突撤销测试模板",
                    "check_items": [
                        {"device_code": "DEV-CONF-001", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}
                    ]
                }
            ],
            "task_packages": [],
            "operator": "测试管理员-冲突"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data5)
        data = response.json()
        for result in data["results"]:
            if result["success"] and result["record_type"] == "template":
                template_ids["冲突测试-变压器"] = int(result["message"].split("ID: ")[1])

        import_data6 = {
            "templates": [],
            "task_packages": [
                {
                    "package_no": f"PKG-CONF-{TEST_TIMESTAMP}",
                    "template_id": template_ids["冲突测试-变压器"],
                    "operator": "测试管理员-冲突"
                }
            ],
            "operator": "测试管理员-冲突"
        }

        response = requests.post(f"{BASE_URL}/api/batch/import/json", json=import_data6)
        data = response.json()
        batch_no_conf_test = data["batch_no"]

        # 发放
        response = requests.post(
            f"{BASE_URL}/api/batch/publish/PKG-CONF-{TEST_TIMESTAMP}",
            params={"operator": "测试管理员-冲突"}
        )
        assert response.status_code == 200

        # 上传第一批读数
        reading_data = {
            "package_no": f"PKG-CONF-{TEST_TIMESTAMP}",
            "readings": [
                {
                    "device_code": "DEV-CONF-001",
                    "item_name": "油温",
                    "reading_value": "75",
                    "collected_at": (datetime.now() - timedelta(hours=1)).isoformat(),
                    "source_type": "offline"
                }
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/readings/upload",
            json=reading_data,
            params={"operator": "测试管理员-冲突"}
        )
        assert response.status_code == 200

        # 上传第二批读数制造冲突
        reading_data2 = {
            "package_no": f"PKG-CONF-{TEST_TIMESTAMP}",
            "readings": [
                {
                    "device_code": "DEV-CONF-001",
                    "item_name": "油温",
                    "reading_value": "85",
                    "collected_at": datetime.now().isoformat(),
                    "source_type": "offline"
                }
            ]
        }
        response = requests.post(
            f"{BASE_URL}/api/readings/upload",
            json=reading_data2,
            params={"operator": "测试管理员-冲突"}
        )
        data = response.json()
        assert data["conflicts_found"] == 1, "应检测到冲突"
        print(f"  已制造冲突，冲突ID: {data['conflicts'][0]['id']}")

        # 校验批次撤销（有冲突且已发放时应拒绝）
        response = requests.get(
            f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no_conf_test}"
        )
        data = print_response(response)
        assert data["allowed"] == False, "有冲突且已发放应不允许撤销"
        assert data["issued_packages"] == 1, "应检测到已发放"
        assert data["open_conflicts"] == 1, "应检测到未解决冲突"
        print("✓ 有未解决冲突且已发放时撤销拦截正常")

        # 撤回发放为草稿
        response = requests.post(
            f"{BASE_URL}/api/task-packages/PKG-CONF-{TEST_TIMESTAMP}/rollback-draft",
            params={"operator": "测试管理员-冲突"}
        )
        # 这个会因为已有读数而失败
        assert response.status_code == 400, "已有读数不能撤回发放"

        # 现在批次状态：有已发放任务包，有读数，有冲突 - 完全不能撤销
        # 这正好验证了我们的撤销条件严格性
        print("✓ 存在读数和冲突时，无法撤回发放也无法撤销批次，数据完整性得到保障")

        # ========== 测试7: 导出过滤已撤销批次 ==========
        print_step(7, "导出过滤 - 默认排除已撤销批次")

        # 默认导出（排除已撤销）
        response = requests.get(f"{BASE_URL}/api/batch/export", params={
            "operator": "测试管理员-撤销"
        })
        data = print_response(response, max_len=600)
        default_count = data["export_count"]

        # 包含已撤销的导出
        response = requests.get(f"{BASE_URL}/api/batch/export", params={
            "operator": "测试管理员-撤销",
            "exclude_revoked": False
        })
        data = print_response(response, max_len=600)
        include_revoked_count = data["export_count"]

        assert include_revoked_count > default_count, "包含已撤销的导出应包含更多记录"
        print(f"  默认排除: {default_count} 条, 包含已撤销: {include_revoked_count} 条")
        print("✓ 导出过滤已撤销批次功能正常")

        # 批次列表也验证
        response = requests.get(f"{BASE_URL}/api/batch/batches", params={
            "operator": "测试管理员-撤销"
        })
        batches_default = response.json()

        response = requests.get(f"{BASE_URL}/api/batch/batches", params={
            "operator": "测试管理员-撤销",
            "exclude_revoked": False
        })
        batches_include = response.json()

        assert len(batches_include) > len(batches_default), "包含已撤销应显示更多批次"
        print("✓ 批次列表过滤已撤销功能正常")

        # ========== 测试8: 重启后数据保持一致 ==========
        print_step(8, "重启验证 - 批次状态、撤销结果、导出过滤保持一致")

        if proc:
            # 记录重启前的关键数据
            batch_before = requests.get(f"{BASE_URL}/api/batch/batches/{batch_no_revoke_test}").json()
            export_default_before = requests.get(f"{BASE_URL}/api/batch/export", params={
                "operator": "测试管理员-撤销"
            }).json()["export_count"]

            audit_before = requests.get(f"{BASE_URL}/api/audit-logs", params={
                "batch_no": batch_no_revoke_test
            }).json()
            audit_before_count = len(audit_before)

            # 停止并重启服务
            stop_service(proc)
            time.sleep(2)
            proc = start_service()

            # 验证重启后的数据
            batch_after = requests.get(f"{BASE_URL}/api/batch/batches/{batch_no_revoke_test}").json()
            assert batch_after["is_revoked"] == 1, "重启后批次撤销状态应保持"
            assert batch_after["revoked_by"] == batch_before["revoked_by"], "重启后撤销人应保持"
            assert batch_after["revocation_reason"] == batch_before["revocation_reason"], "重启后撤销原因应保持"
            assert batch_after["status"] == "revoked", "重启后批次状态应保持"
            print("✓ 重启后批次撤销状态保持一致")

            # 验证导出过滤
            export_default_after = requests.get(f"{BASE_URL}/api/batch/export", params={
                "operator": "测试管理员-撤销"
            }).json()["export_count"]
            assert export_default_after == export_default_before, "重启后导出过滤结果应保持一致"
            print("✓ 重启后导出过滤保持一致")

            # 验证审计日志
            audit_after = requests.get(f"{BASE_URL}/api/audit-logs", params={
                "batch_no": batch_no_revoke_test
            }).json()
            assert len(audit_after) >= audit_before_count, "重启后审计日志不应丢失"
            print("✓ 重启后审计日志保持完整")

            # 验证重复撤销仍然被拦截
            response = requests.post(
                f"{BASE_URL}/api/batch/revoke/batch/{batch_no_revoke_test}",
                json={"reason": "重启后重复撤销测试"},
                params={"operator": "测试管理员-重启后"}
            )
            assert response.status_code == 400, "重启后重复撤销仍应被拦截"
            assert "已被撤销" in response.json()["detail"], "重启后错误信息应保持清晰"
            print("✓ 重启后重复撤销拦截正常")

        else:
            print("⚠️  外部服务，跳过重启测试")

        # ========== 测试9: 操作人贯穿所有接口验证 ==========
        print_step(9, "操作人贯穿验证 - 预检、导入、撤销、日志查询")

        # 预检操作人
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "batch_no": batch_no_precheck_json,
            "action": "batch_precheck"
        })
        logs = response.json()
        assert logs[0]["operator"] == "测试管理员-JSON预检", "预检操作人不正确"
        print("✓ 预检操作人记录正确")

        # 导入操作人
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "batch_no": batch_no_revoke_test,
            "action": "batch_import"
        })
        logs = response.json()
        assert logs[0]["operator"] == "测试管理员-撤销", "导入操作人不正确"
        print("✓ 导入操作人记录正确")

        # 撤销操作人
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "batch_no": batch_no_revoke_test,
            "action": "batch_revoke"
        })
        logs = response.json()
        assert logs[0]["operator"] == "测试管理员-撤销", "撤销操作人不正确"
        print("✓ 撤销操作人记录正确")

        # 日志查询按操作人过滤
        response = requests.get(f"{BASE_URL}/api/audit-logs", params={
            "operator": "测试管理员-撤销"
        })
        logs = response.json()
        assert len(logs) >= 3, "按操作人过滤审计日志应返回多条记录"
        for log in logs:
            assert log["operator"] == "测试管理员-撤销", "过滤结果操作人应一致"
        print("✓ 审计日志按操作人过滤正常")

        # 批次列表按操作人过滤
        response = requests.get(f"{BASE_URL}/api/batch/batches", params={
            "operator": "测试管理员-撤销",
            "exclude_revoked": False
        })
        batches = response.json()
        assert len(batches) >= 1, "按操作人过滤批次应返回结果"
        for batch in batches:
            assert batch["operator"] == "测试管理员-撤销", "过滤结果操作人应一致"
        print("✓ 批次列表按操作人过滤正常")

        print("\n" + "=" * 70)
        print("✅ 批量导入预检和撤销功能回归测试全部通过！")
        print(f"   测试批次号:")
        print(f"   - JSON预检: {batch_no_precheck_json}")
        print(f"   - CSV预检: {batch_no_precheck_csv}")
        print(f"   - 撤销测试: {batch_no_revoke_test}")
        print("=" * 70)

        return True

    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 无法连接到服务，请先启动服务: python main.py")
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
    success = test_precheck_and_revoke()
    sys.exit(0 if success else 1)
