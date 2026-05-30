from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
from models.entities import ChargeMode
from controllers.system_controller import SystemController
from models.system_report import SystemReport
import uuid

app = Flask(__name__)
system = SystemController(waiting_capacity=10, max_queue_length=5)

# 全局用户会话
current_user = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    global current_user
    data = request.get_json()
    user_id = data.get('user_id')
    password = data.get('password')
    
    if system.userLogin(user_id, password):
        current_user = user_id
        return jsonify({
            'success': True,
            'user_id': user_id,
            'message': '登录成功'
        })
    else:
        return jsonify({
            'success': False,
            'message': '用户名或密码错误'
        }), 401

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    user_id = data.get('user_id', '').strip()
    password = data.get('password', '').strip()

    if not user_id or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    if system.userExists(user_id):
        return jsonify({'success': False, 'message': '用户名已存在'}), 409

    if system.registerUser(user_id, password, float(data.get('battery_capacity', 60))):
        return jsonify({'success': True, 'message': '注册成功，请登录'})
    else:
        return jsonify({'success': False, 'message': '注册失败'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    global current_user
    current_user = None
    return jsonify({'success': True})

@app.route('/api/user/status', methods=['GET'])
def get_user_status():
    return jsonify({
        'logged_in': current_user is not None,
        'user_id': current_user
    })

@app.route('/api/charge/request', methods=['POST'])
def submit_charge_request():
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    data = request.get_json()
    charge_mode = data.get('charge_mode')  # 'Fast' or 'Trickle'
    need_power = float(data.get('need_power', 30))
    
    req_id = system.submitChargeReq(current_user, charge_mode, need_power, datetime.now())
    
    return jsonify({
        'success': True,
        'request_id': req_id,
        'message': '充电请求已提交'
    })

@app.route('/api/request/<req_id>/modify', methods=['PUT'])
def modify_request(req_id):
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    data = request.get_json()
    opt_type = data.get('opt_type')  # 'mode' or 'power'
    charge_mode = data.get('charge_mode')
    need_power = float(data.get('need_power', 30))
    
    system.modifyChargeReq(req_id, opt_type, charge_mode, need_power)
    
    return jsonify({
        'success': True,
        'message': '请求已修改'
    })

@app.route('/api/request/<req_id>/cancel', methods=['POST'])
def cancel_request(req_id):
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    system.cancelChargeReq(req_id, datetime.now())
    
    return jsonify({
        'success': True,
        'message': '请求已取消'
    })

@app.route('/api/pile/<pile_id>/finish', methods=['POST'])
def finish_charging(pile_id):
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    system.finishCharge(pile_id, datetime.now())
    
    return jsonify({
        'success': True,
        'message': '充电已完成'
    })

@app.route('/api/pile/<pile_id>/fault', methods=['POST'])
def report_fault(pile_id):
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    data = request.get_json()
    fault_info = data.get('fault_info', '未知故障')
    dispatch_strategy = data.get('dispatch_strategy', 'priority')
    
    system.catchFault(pile_id, fault_info, datetime.now(), dispatch_strategy)
    
    return jsonify({
        'success': True,
        'message': '故障已上报'
    })

@app.route('/api/pile/<pile_id>/resolve-fault', methods=['POST'])
def resolve_fault(pile_id):
    if current_user is None:
        return jsonify({'success': False, 'message': '请先登录'}), 401
    
    system.resolveFault(pile_id, datetime.now())
    
    return jsonify({
        'success': True,
        'message': '故障已修复'
    })

@app.route('/api/stats/piles', methods=['GET'])
def get_pile_stats():
    pile_report = SystemReport.generatePileReport(system.chargingArea.getAllPiles())
    return jsonify(pile_report)

@app.route('/api/stats/billing', methods=['GET'])
def get_billing_stats():
    billing_report = SystemReport.generateBillingReport(system.chargingDetails)
    return jsonify(billing_report)

@app.route('/api/stats/faults', methods=['GET'])
def get_fault_stats():
    fault_report = SystemReport.generateFaultReport(system.faultRecords)
    return jsonify(fault_report)

@app.route('/api/waiting-area', methods=['GET'])
def get_waiting_area():
    requests_info = []
    for req in system.waitingArea.currentRequests:
        requests_info.append({
            'request_id': req.requestId,
            'user_id': req.userId,
            'charge_mode': req.chargeMode,
            'need_power': req.needPower,
            'status': req.status,
            'queue_number': req.queueNumber.getQueueString() if req.queueNumber else None
        })
    return jsonify({
        'max_capacity': system.waitingArea.maxCapacity,
        'current_count': len(system.waitingArea.currentRequests),
        'requests': requests_info
    })

@app.route('/api/charging-area', methods=['GET'])
def get_charging_area():
    piles_info = []
    for pile in system.chargingArea.getAllPiles():
        pile_type = '快充' if pile.pileId.startswith('F') else '慢充'
        queue_items = []
        for req in pile.currentQueue:
            queue_items.append({
                'request_id': req.requestId,
                'user_id': req.userId,
                'charge_mode': req.chargeMode,
                'need_power': req.needPower,
                'queue_number': req.queueNumber.getQueueString() if req.queueNumber else None,
                'status': req.status,
            })
        current = None
        if pile.currentChargingRequest:
            req = pile.currentChargingRequest
            current = {
                'request_id': req.requestId,
                'user_id': req.userId,
                'charge_mode': req.chargeMode,
                'need_power': req.needPower,
                'queue_number': req.queueNumber.getQueueString() if req.queueNumber else None,
                'status': req.status,
            }
        piles_info.append({
            'pile_id': pile.pileId,
            'pile_type': pile_type,
            'power': pile.power,
            'status': pile.status,
            'queue_length': len(pile.currentQueue),
            'max_queue_length': pile.maxQueueLength,
            'total_charge_count': pile.totalChargeCount,
            'total_charge_power': round(pile.totalChargePower, 2),
            'total_charge_duration': round(pile.totalChargeDuration, 2),
            'current_charging': current,
            'queue': queue_items,
        })
    return jsonify({'piles': piles_info})


@app.route('/api/system/overview', methods=['GET'])
def get_system_overview():
    piles = system.chargingArea.getAllPiles()
    available = fault = 0
    total_queue = 0
    for pile in piles:
        if pile.status == 'Available':
            available += 1
        elif pile.status == 'Fault':
            fault += 1
        total_queue += len(pile.currentQueue)

    return jsonify({
        'waiting_count': len(system.waitingArea.currentRequests),
        'waiting_capacity': system.waitingArea.maxCapacity,
        'available_piles': available,
        'charging_piles': sum(1 for p in piles if p.status == 'Charging'),
        'fault_piles': fault,
        'total_queue': total_queue,
        'is_call_paused': system.schedulingController.isCallPaused,
        'batch_threshold': system._getBatchTriggerThreshold(),
        'total_vehicles': system._getTotalVehicleCount(),
    })


@app.route('/api/stats/billing/details', methods=['GET'])
def get_billing_details():
    details = []
    for d in system.chargingDetails[-20:]:
        details.append({
            'detail_id': d.detailId,
            'pile_id': d.pileId,
            'energy_amount': round(d.energyAmount, 2),
            'start_time': d.startTime.strftime('%Y-%m-%d %H:%M'),
            'stop_time': d.stopTime.strftime('%Y-%m-%d %H:%M'),
            'charging_fee': round(d.chargingFee, 2),
            'service_fee': round(d.serviceFee, 2),
            'total_fee': round(d.totalFee, 2),
        })
    details.reverse()
    return jsonify({'details': details})


@app.route('/api/stats/faults/details', methods=['GET'])
def get_fault_details():
    records = []
    for r in system.faultRecords[-20:]:
        records.append({
            'record_id': r.recordId,
            'pile_id': r.pileId,
            'fault_time': r.faultTime.strftime('%Y-%m-%d %H:%M'),
            'fault_reason': r.faultReason,
            'is_resolved': r.isResolved,
        })
    records.reverse()
    return jsonify({'records': records})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
