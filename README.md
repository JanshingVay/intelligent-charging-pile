
# 智能充电桩调度计费系统

## 项目概述
这是一个智能充电桩调度计费系统，包含**完整的Web界面**和**纯Python后端**，采用 MVC 架构设计，实现了完整的充电管理、调度和计费功能。

## 系统架构
- **后端**: Flask + Python
- **前端**: Bootstrap 5 + JavaScript
- **架构模式**: MVC (Model-View-Controller)
- **Web版本**: 完整的用户界面，易于使用
- **纯Python版本**: 不依赖第三方库的控制台版本

## 项目结构
```
ZNCDZ/
├── models/                    # 模型层
│   ├── entities.py           # 核心实体类
│   ├── piles.py              # 充电桩类
│   ├── areas.py              # 物理区域类
│   └── system_report.py      # 系统报表类
├── controllers/              # 控制器层
│   ├── system_controller.py  # 系统主控制器
│   ├── scheduling_controller.py  # 调度控制器
│   └── billing_controller.py # 计费控制器
├── templates/
│   └── index.html            # Web前端界面
├── app.py                    # Web后端主程序
├── requirements.txt          # Python依赖
├── run.bat                   # 快速启动脚本
├── charging_system.py        # 纯Python单文件版本
├── final_system.py           # 纯Python单文件版本(备份)
├── main.py                   # MVC架构纯Python版本
├── requirements.md           # 原始需求文档
└── README.md                 # 本文件
```

## 核心功能

### 1. 用户管理
- 用户登录验证
- 预配置用户账号

### 2. 充电管理
- 提交充电请求（快充/慢充）
- 修改充电请求（模式/电量）
- 取消充电请求
- 完成充电

### 3. 调度算法
- **基础调度**: 选择等待时间+充电时间最短的充电桩
- **优先级调度**: 故障发生时优先处理等待队列
- **时间顺序调度**: 按原始排队时间重新分配
- **故障恢复调度**: 故障修复后重新分配

### 4. 计费规则
- **峰时 (10:00-15:00, 18:00-21:00)**: 1.0元/度
- **平时 (7:00-10:00, 15:00-18:00, 21:00-23:00)**: 0.7元/度
- **谷时 (23:00-次日7:00)**: 0.4元/度
- **服务费**: 固定 0.8元/度
- 支持跨时段分段计费

### 5. 充电桩管理
- 3个快充桩（功率30kW）
- 2个慢充桩（功率10kW）
- 故障检测和修复

### 6. 系统报表
- 充电桩状态报告
- 计费统计报告
- 故障记录报告

## 核心类设计

### 模型层 (Models)
- `User`: 用户账号信息
- `ElectricVehicle`: 电动车信息
- `QueueNumber`: 排队号码
- `ChargingRequest`: 充电请求
- `ChargingDetail`: 充电详单
- `FaultRecord`: 故障记录
- `ChargingPile`: 充电桩基类
  - `FastChargingPile`: 快充桩
  - `TrickleChargingPile`: 慢充桩
- `WaitingArea`: 等候区
- `ChargingArea`: 充电区
- `SystemReport`: 系统报表

### 控制器层 (Controllers)
- `SystemController`: 系统主控制器，统一对外接口
- `SchedulingController`: 调度控制器，处理所有调度逻辑
- `BillingController`: 计费控制器，处理所有计费逻辑

## 使用说明

### 方式一：Web界面版本（推荐）

1. **安装依赖**
```bash
pip install -r requirements.txt
# 或
pip install flask
```

2. **启动Web应用**
```bash
# Windows
run.bat
# 或
python app.py
```

3. **访问系统**
在浏览器打开: http://localhost:5000

4. **Web功能**
- 用户登录（默认：user1/123456）
- 提交充电请求（快充/慢充）
- 查看等候区和充电区状态
- 完成充电、上报/修复故障
- 查看实时统计报表

### 方式二：纯Python版本
```bash
# MVC架构版本
python main.py

# 单文件版本
python charging_system.py
```

### 代码示例
```python
from final_system import SystemController, CHARGE_MODE_FAST
from datetime import datetime, timedelta

# 创建系统
system = SystemController(waiting_capacity=10, max_queue_length=5)

# 用户登录
if system.userLogin("user1", "123456"):
    # 提交充电请求
    req_id = system.submitChargeReq("user1", CHARGE_MODE_FAST, 30.0, datetime.now())
    
    # 完成充电
    finish_time = datetime.now() + timedelta(hours=2)
    system.finishCharge("F1", finish_time)
```

## 设计特点

1. **MVC 架构**: 清晰的分层设计，模型与控制器解耦
2. **继承多态**: 充电桩采用基类 + 子类设计，支持扩展
3. **完整调度**: 实现了需求中所有调度策略
4. **精确计费**: 支持跨时段分段计费
5. **可扩展性**: 易于添加新的调度策略或计费规则
