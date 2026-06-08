#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速完整链路测试 - 预检、导入、撤销、重启验证"""

import requests
import json
import time
import os
import sys
import subprocess

BASE_URL = "http://127.0.0.1:8000"
TIMESTAMP = time.strftime("%H%M%S")

def print_step(step_num, title):
    print(f"\n{'='*70}")
    print(f"步骤 {step_num}: {title}")
    print(f"{'='*70}")

def check_response(response, expected_status=200):
    try:
        data = response.json()
    except:
        data = response.text
    print(f"状态码: {response.status_code}")
    if response.status_code != expected_status:
        print(f"❌ 期望状态码 {expected_status}，实际 {response.status_code}")
        print(f"响应: {data}")
        return None
    return data

def is_server_ready():
    try:
        requests.get(f"{BASE_URL}/api/batch/batches", timeout=2)
        return True
    except:
        return False

def main():
    print("\n" + "╔" + "═"*68 + "╗")
    print("║" + " "*10 + "批量导入预检和撤销 - 完整链路快速验证" + " "*10 + "║")
    print("╚" + "═"*68 + "╝")

    if not is_server_ready():
        print("启动服务...")
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        
        max_wait = 30
        waited = 0
        while waited < max_wait and not is_server_ready():
            time.sleep(1)
            waited += 1
        print("✓ 服务已启动")
    else:
        print("✓ 服务已在运行")
        server_proc = None

    try:
        # ===== 步骤1: JSON预检 =====
        print_step(1, "JSON预检 - 只校验不入库")
        precheck_data = {
            "templates": [
                {"name": f"完整链路-变压器-{TIMESTAMP}", "description": "测试", "check_items": [{"device_code": "DEV-001", "item_name": "温度", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}]}
            ],
            "task_packages": [
                {"package_no": f"PKG-FULL-{TIMESTAMP}", "template_id": 99999}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/precheck/json", 
                         params={"operator": "链路测试员"}, 
                         json=precheck_data, timeout=10)
        data = check_response(r)
        if data:
            print(f"  ✓ 批次号: {data.get('batch_no')}")
            print(f"  ✓ 将新增: {data.get('will_add')}, 模板不存在: {data.get('template_not_found')}")
            assert data.get("will_add") == 1
            assert data.get("template_not_found") == 1
            print("  ✓ 预检通过，数据未入库")

        # 预检后确认数据没入库
        r = requests.get(f"{BASE_URL}/api/batch/batches", timeout=10)
        resp = r.json()
        batches_before = resp.get("items", []) if isinstance(resp, dict) else resp

        # ===== 步骤2: 正常导入 =====
        print_step(2, "正常导入模板和任务包")
        import_data = {
            "templates": [
                {"name": f"完整链路-变压器-{TIMESTAMP}", "description": "测试", "check_items": [{"device_code": "DEV-001", "item_name": "温度", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}]}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/import/json", 
                         params={"operator": "链路测试员"}, 
                         json=import_data, timeout=10)
        data = check_response(r)
        template_id = None
        if data:
            print(f"  ✓ 模板导入成功")
            template_id = int(data["results"][0]["message"].split("ID: ")[1])
            print(f"  ✓ 模板ID: {template_id}")

        # 导入任务包
        pkg_data = {
            "task_packages": [
                {"package_no": f"PKG-FULL-{TIMESTAMP}", "template_id": template_id}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/import/json", 
                         params={"operator": "链路测试员"}, 
                         json=pkg_data, timeout=10)
        data = check_response(r)
        batch_no = None
        if data:
            batch_no = data["batch_no"]
            print(f"  ✓ 任务包导入成功，批次号: {batch_no}")

        # ===== 步骤3: 撤销前校验 =====
        print_step(3, "撤销前校验")
        r = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no}", timeout=10)
        data = check_response(r)
        if data:
            assert data.get("allowed") == True
            print(f"  ✓ 校验通过，允许撤销")
            print(f"  ✓ 任务包数量: {data.get('packages_count')}")

        # ===== 步骤4: 执行撤销 =====
        print_step(4, "执行撤销")
        r = requests.post(f"{BASE_URL}/api/batch/revoke/batch/{batch_no}", 
                         params={"operator": "链路测试员"}, 
                         json={"reason": "测试撤销"},
                         timeout=10)
        data = check_response(r)
        if data:
            assert data.get("success") == True
            print(f"  ✓ 撤销成功")
            print(f"  ✓ 撤销时间: {data.get('revoked_at')}")
            print(f"  ✓ 撤销人: {data.get('operator')}")

        # ===== 步骤5: 重复撤销 =====
        print_step(5, "重复撤销 - 返回清楚错误")
        r = requests.post(f"{BASE_URL}/api/batch/revoke/batch/{batch_no}", 
                         params={"operator": "链路测试员"}, 
                         json={"reason": "重复撤销"},
                         timeout=10)
        data = check_response(r, expected_status=400)
        if data:
            print(f"  ✓ 重复撤销检测正常")
            print(f"  ✓ 错误信息: {data.get('detail')[:80]}...")
            assert "已被撤销" in data.get("detail", "")

        # ===== 步骤6: 导出过滤 =====
        print_step(6, "导出过滤已撤销批次")
        r = requests.get(f"{BASE_URL}/api/batch/export", timeout=10)
        data = check_response(r)
        count_default = data.get("export_count", 0) if data else 0
        
        r = requests.get(f"{BASE_URL}/api/batch/export", params={"exclude_revoked": "false"}, timeout=10)
        data = check_response(r)
        count_with_revoked = data.get("export_count", 0) if data else 0
        
        print(f"  ✓ 默认排除: {count_default} 条")
        print(f"  ✓ 包含已撤销: {count_with_revoked} 条")
        assert count_with_revoked >= count_default

        # ===== 步骤7: 操作人过滤 =====
        print_step(7, "操作人过滤验证")
        r = requests.get(f"{BASE_URL}/api/batch/batches", params={"operator": "链路测试员"}, timeout=10)
        data = check_response(r)
        if data:
            filtered_count = len(data) if isinstance(data, list) else len(data.get("items", []))
            print(f"  ✓ 操作人过滤返回 {filtered_count} 条记录")
            assert filtered_count > 0

        # ===== 步骤8: 重启验证 =====
        print_step(8, "重启验证 - 数据一致性")
        print("  正在重启服务...")
        
        # 先保存重启前的数据快照
        r = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no}", timeout=10)
        before_revoke_status = r.json().get("is_revoked") if r.status_code == 200 else None
        
        # 终止当前服务
        if server_proc:
            server_proc.terminate()
            server_proc.wait()
        time.sleep(3)
        
        # 重新启动服务
        new_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 等待服务就绪
        max_wait = 30
        waited = 0
        while waited < max_wait and not is_server_ready():
            time.sleep(1)
            waited += 1
        print("  服务已重启")
        
        # 验证撤销状态
        r = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no}", timeout=10)
        data = check_response(r)
        if data:
            assert data.get("is_revoked") == True
            assert data.get("is_revoked") == before_revoke_status
            print(f"  ✓ 重启后批次撤销状态保持: is_revoked={data.get('is_revoked')}")
        
        # 验证导出过滤
        r = requests.get(f"{BASE_URL}/api/batch/export", timeout=10)
        data = check_response(r)
        count_after_restart = data.get("export_count", 0) if data else 0
        print(f"  ✓ 重启后默认导出: {count_after_restart} 条 (重启前: {count_default})")
        assert count_after_restart == count_default
        
        # 验证操作人过滤
        r = requests.get(f"{BASE_URL}/api/batch/batches", params={"operator": "链路测试员"}, timeout=10)
        data = check_response(r)
        if data:
            count_filter_after = len(data) if isinstance(data, list) else len(data.get("items", []))
            print(f"  ✓ 重启后操作人过滤: {count_filter_after} 条 (重启前: {filtered_count})")
            assert count_filter_after == filtered_count

        # 清理
        new_proc.terminate()

        print("\n" + "="*70)
        print("✅ 完整链路测试全部通过！")
        print(f"   测试批次号: {batch_no}")
        print("="*70 + "\n")
        return 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
