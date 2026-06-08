#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现和验证同批新增模板被任务包引用的问题"""

import requests
import json
import time
import sys
import subprocess

BASE_URL = "http://127.0.0.1:8000"
TIMESTAMP = time.strftime("%H%M%S")

def is_server_ready():
    try:
        requests.get(f"{BASE_URL}/api/batch/batches", timeout=2)
        return True
    except:
        return False

def print_step(step_num, title):
    print(f"\n{'='*70}")
    print(f"步骤 {step_num}: {title}")
    print(f"{'='*70}")

def check_response(response, expected_status=200, context=""):
    try:
        data = response.json()
    except:
        data = response.text
    print(f"状态码: {response.status_code}")
    if response.status_code != expected_status:
        print(f"❌ {context} 期望状态码 {expected_status}，实际 {response.status_code}")
        print(f"响应: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")
        return None
    return data

def main():
    print("\n" + "╔" + "═"*68 + "╗")
    print("║" + " "*8 + "同批新增模板引用测试 - 复现与验证" + " "*8 + "║")
    print("╚" + "═"*68 + "╝")

    # 启动服务
    server_proc = None
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

    batch_no = None
    template_id = None

    try:
        # ===== 步骤1: 复现问题 - 同批导入模板+任务包（用template_id）=====
        print_step(1, "复现问题 - 同批导入（用template_id）")
        print("  尝试用 template_id=99999 引用同批模板（这是不可能的）")
        bad_data = {
            "templates": [
                {"name": f"同批测试-变压器-{TIMESTAMP}", "description": "测试", 
                 "check_items": [{"device_code": "DEV-001", "item_name": "温度", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}]}
            ],
            "task_packages": [
                {"package_no": f"PKG-SAME-{TIMESTAMP}", "template_id": 99999}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/import/json", 
                         params={"operator": "同批测试员"}, 
                         json=bad_data, timeout=10)
        data = check_response(r, context="问题复现")
        if data:
            print(f"  模板导入结果: {data['results'][0]['success']} - {data['results'][0]['message']}")
            print(f"  任务包导入结果: {data['results'][1]['success']} - {data['results'][1]['message']}")
            if data['results'][0]['success'] and not data['results'][1]['success']:
                print("  ✅ 成功复现半成功问题：模板入库但任务包因模板不存在失败")
            else:
                print("  ⚠️  未复现预期的半成功问题")

        # ===== 步骤2: 预检同批引用 =====
        print_step(2, "预检 - 同批新增模板被任务包引用")
        precheck_data = {
            "templates": [
                {"name": f"预检同批-变压器-{TIMESTAMP}", "description": "测试", 
                 "check_items": [{"device_code": "DEV-002", "item_name": "油温", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}]}
            ],
            "task_packages": [
                {"package_no": f"PKG-PRE-{TIMESTAMP}", 
                 "template_name": f"预检同批-变压器-{TIMESTAMP}"}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/precheck/json", 
                         params={"operator": "同批测试员"}, 
                         json=precheck_data, timeout=10)
        data = check_response(r, context="预检同批引用")
        if data:
            print(f"  响应: {json.dumps(data, ensure_ascii=False, indent=2)[:800]}")
            template_item = data['items'][0]
            pkg_item = data['items'][1]
            print(f"  模板: {template_item['check_result']} - {template_item['message']}")
            print(f"  任务包: {pkg_item['check_result']} - {pkg_item['message']}")
            if template_item['check_result'] == 'will_add' and pkg_item['check_result'] == 'will_add':
                print("  ✅ 预检正确：同批新增模板可被任务包引用")
            else:
                print("  ❌ 预检错误：同批新增模板未被正确识别")

        # ===== 步骤3: 确认导入 - 同批模板+任务包（用template_name）=====
        print_step(3, "确认导入 - 同批模板+任务包（用template_name引用）")
        import_data = {
            "templates": [
                {"name": f"导入同批-变压器-{TIMESTAMP}", "description": "测试", 
                 "check_items": [{"device_code": "DEV-003", "item_name": "温度", "unit": "°C", "standard_value": "≤85", "tolerance": "±5"}]}
            ],
            "task_packages": [
                {"package_no": f"PKG-IMPORT-{TIMESTAMP}", 
                 "template_name": f"导入同批-变压器-{TIMESTAMP}"}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/import/json", 
                         params={"operator": "同批测试员"}, 
                         json=import_data, timeout=10)
        data = check_response(r, context="确认导入")
        if data:
            batch_no = data['batch_no']
            print(f"  批次号: {batch_no}")
            print(f"  总记录: {data['total_records']}, 成功: {data['success_count']}, 失败: {data['failed_count']}")
            for i, res in enumerate(data['results']):
                print(f"  记录{i+1}: {'✅' if res['success'] else '❌'} {res['record_type']} - {res['identifier']} - {res['message']}")
            
            if data['success_count'] == 2 and data['failed_count'] == 0:
                print("  ✅ 同批导入成功！模板和任务包都成功")
                # 解析模板ID
                msg = data['results'][0]['message']
                template_id = int(msg.split("ID: ")[1])
                print(f"  新模板ID: {template_id}")
            else:
                print("  ❌ 同批导入失败，存在半成功问题")

        # ===== 步骤4: 验证非法引用仍报错 =====
        print_step(4, "验证 - 非法模板引用仍清楚报错")
        bad_ref_data = {
            "templates": [],
            "task_packages": [
                {"package_no": f"PKG-BAD-{TIMESTAMP}", "template_id": 999999}
            ]
        }
        r = requests.post(f"{BASE_URL}/api/batch/import/json", 
                         params={"operator": "同批测试员"}, 
                         json=bad_ref_data, timeout=10)
        data = check_response(r, context="非法引用测试")
        if data:
            if data['failed_count'] == 1 and "模板不存在" in data['results'][0]['message']:
                print("  ✅ 非法模板引用正确报错")
            else:
                print("  ❌ 非法引用未正确处理")

        # ===== 步骤5: 验证按批次撤销 =====
        print_step(5, "验证 - 按批次撤销能删除本批创建的数据")
        if batch_no:
            r = requests.get(f"{BASE_URL}/api/batch/revoke/batch/validate/{batch_no}", timeout=10)
            data = check_response(r, context="撤销前校验")
            if data and data.get('allowed'):
                r = requests.post(f"{BASE_URL}/api/batch/revoke/batch/{batch_no}", 
                                 params={"operator": "同批测试员"}, 
                                 json={"reason": "测试撤销"},
                                 timeout=10)
                data = check_response(r, context="执行撤销")
                if data and data.get('success'):
                    print(f"  ✅ 撤销成功，删除 {data['revoked_templates']} 个模板和 {data['revoked_packages']} 个任务包")
                    
                    # 验证数据已删除
                    if template_id:
                        r = requests.get(f"{BASE_URL}/api/templates/{template_id}", timeout=10)
                        if r.status_code == 404:
                            print("  ✅ 模板已被删除")
                        else:
                            print("  ❌ 模板未被正确删除")
                else:
                    print("  ❌ 撤销失败")
            else:
                print(f"  ⚠️  无法撤销: {data.get('reason') if data else '未知原因'}")

        # ===== 步骤6: 验证预检不落库 =====
        print_step(6, "验证 - 预检不落库")
        r = requests.get(f"{BASE_URL}/api/batch/batches", params={"operator": "同批测试员"}, timeout=10)
        batches = r.json() if r.status_code == 200 else []
        print(f"  操作人相关批次共 {len(batches)} 个")
        # 检查是否有预检批次（预检不应该创建批次记录）
        pre_batches = [b for b in batches if 'precheck' in b.get('source_type', '').lower() or b.get('status') == 'precheck']
        if len(pre_batches) == 0:
            print("  ✅ 预检没有创建批次记录，正确不落库")
        else:
            print(f"  ⚠️  发现 {len(pre_batches)} 个预检批次，可能有问题")

        print("\n" + "="*70)
        print("✅ 测试完成！")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if server_proc:
            server_proc.terminate()

if __name__ == "__main__":
    main()
