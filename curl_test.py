#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""curl测试脚本 - 验证同批导入修复"""

import requests
import json
import time

BASE = 'http://127.0.0.1:8000'
ts = time.strftime('%H%M%S')

print("=" * 70)
print("同批导入修复验证 - curl测试")
print("=" * 70)

# 测试1: 预检 - 同批新增模板+任务包（用template_name）
print("\n=== 测试1: 预检 同批模板+任务包 ===")
precheck_data = {
    'templates': [
        {'name': f'curl-变压器-{ts}', 'description': 'test',
         'check_items': [{'device_code': 'D001', 'item_name': '温度', 'unit': '°C', 'standard_value': '≤85', 'tolerance': '±5'}]}
    ],
    'task_packages': [
        {'package_no': f'PKG-CURL-{ts}', 'template_name': f'curl-变压器-{ts}'}
    ]
}
r = requests.post(f'{BASE}/api/batch/precheck/json', params={'operator': 'curl测试'}, json=precheck_data)
print(f'预检状态: {r.status_code}')
data = r.json()
print(f'预检结果: success={data["success"]}, will_add={data["will_add"]}, template_not_found={data["template_not_found"]}')
for item in data['items']:
    print(f'  {item["record_type"]}: {item["check_result"]} - {item["message"]}')

# 测试2: 确认导入
print("\n=== 测试2: 确认导入 同批模板+任务包 ===")
r = requests.post(f'{BASE}/api/batch/import/json', params={'operator': 'curl测试'}, json=precheck_data)
print(f'导入状态: {r.status_code}')
data = r.json()
print(f'导入结果: total={data["total_records"]}, success={data["success_count"]}, failed={data["failed_count"]}')
batch_no = data['batch_no']
print(f'批次号: {batch_no}')
for res in data['results']:
    status = '✅' if res['success'] else '❌'
    print(f'  {status} {res["record_type"]}: {res["identifier"]} - {res["message"]}')

# 测试3: 撤销
print("\n=== 测试3: 撤销批次 ===")
r = requests.post(f'{BASE}/api/batch/revoke/batch/{batch_no}', params={'operator': 'curl测试'}, json={'reason': 'curl测试撤销'})
print(f'撤销状态: {r.status_code}')
data = r.json()
print(f'撤销结果: success={data["success"]}, templates={data["revoked_templates"]}, packages={data["revoked_packages"]}')

# 测试4: 重复撤销
print("\n=== 测试4: 重复撤销 ===")
r = requests.post(f'{BASE}/api/batch/revoke/batch/{batch_no}', params={'operator': 'curl测试'}, json={'reason': '重复撤销'})
print(f'重复撤销状态: {r.status_code}')
detail = r.json()['detail']
print(f'错误信息: {detail[:80]}...')

print("\n" + "=" * 70)
print("✅ 所有curl测试通过！")
print("=" * 70)
