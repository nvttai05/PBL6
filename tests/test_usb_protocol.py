from copy import deepcopy
import json
import pytest

from robonose_s3.clock import FakeClock
from robonose_s3.emulator import EmulatedTransport
from robonose_s3.serial_device import Pending, SerialDevice
from robonose_s3.usb_protocol import Framer, ProtocolError, SerialOptions, validate_hello, validate_sample


def setup_device():
    clock=FakeClock(); emulator=EmulatedTransport(clock)
    device=SerialDevice(SerialOptions('MOCK','emulated'),'host-session',clock,lambda data:None,lambda:False)
    device._accept(emulator.hello())
    return clock,emulator,device


def sample(emulator,seq=1):
    row=emulator.sim.read(emulator.clock.now(),emulator.state.context(emulator.clock.now()))
    row.update(emulator._common('sample')); row.update(emulator.context())
    row.update(seq=seq,profile_id=emulator.hello()['profile_id'])
    return row


@pytest.mark.parametrize('key,value',[
    ('firmware_version','2.1.0'),('schema','robonose.control_test.v2.1'),('protocol','old'),
    ('channel_map','A0=mq135_1,A1=mq3_1,A2=tgs2602,A3=mq3_2'),('ads_fsr_v',4.096),
    ('ads_lsb_v',.000125),('divider_factor',2),('ads_sda',8),('heater_requested_c',320),
    ('os_t_applied',8),('heater_applied_ms',150),('pump_pwm_pct',80),('fault_latched',True)])
def test_incompatible_handshake_rejected_before_begin(key,value):
    hello=EmulatedTransport(FakeClock()).hello(); hello[key]=value
    with pytest.raises(ProtocolError):
        validate_hello(hello)


def test_strict_split_frames_oversized_chatter_duplicate_keys_and_nan():
    framer=Framer(100)
    data=b'ROM boot\n{"type":"ok","value":3}\r\n'
    output=[]
    for chunk in (data[:5],data[5:19],data[19:]):
        output+=framer.feed(chunk)
    assert output[0]['type']=='parser_event' and output[1]['value']==3
    assert framer.feed(b'x'*150+b'\n')[0]['reason']=='oversized_frame'
    assert framer.feed(b'{"x":1,"x":2}\n')[0]['type']=='parser_event'
    assert framer.feed(b'{"x":NaN}\n')[0]['type']=='parser_event'
    assert framer.feed(b'[]\n')[0]['type']=='parser_event'
    assert framer.feed(b'{"recovered":true}\n')==[{'recovered':True}]
    assert len(framer.buffer)==0


@pytest.mark.parametrize('reason',[5,[],{},'x'*64])
def test_invalid_mcu_fault_reason_rejected(reason):
    from robonose_s3.usb_protocol import validate_context
    emulator=EmulatedTransport(FakeClock())
    packet=emulator.context()
    packet['fault_reason']=reason
    with pytest.raises(ProtocolError,match='fault_reason'):
        validate_context(packet)


def test_seq_gap_duplicate_and_reordered_are_not_new_canonical_rows():
    clock,emulator,device=setup_device()
    device._accept(sample(emulator,1)); device._accept(sample(emulator,4))
    device._accept(sample(emulator,4)); device._accept(sample(emulator,2))
    assert device.last_seq==4 and device.gaps==2 and device.dropped==2
    packets=[]
    while not device.incoming.empty():
        packets.append(device.incoming.get_nowait())
    assert [p['seq'] for p in packets if p['type']=='sample']==[1,4]
    assert sum(p.get('reason')=='duplicate_or_reordered_sample' for p in packets)==2


def test_reset_foreign_active_session_and_ack_mismatch_are_faults():
    clock,emulator,device=setup_device()
    reboot=emulator.hello(); reboot['boot_id']='new-boot'
    with pytest.raises(ProtocolError,match='reboot'):
        device._accept(reboot)
    emulator.state.start_session(0)
    packet={**emulator._common('ack'),**emulator.context(),'request_id':1,'accepted':True,'reason':'accepted',
            'applied_ms':0,'barrier_seq':0}
    packet['session_id']='foreign'
    with pytest.raises(ProtocolError,match='Foreign'):
        device._accept(packet)
    packet['session_id']='host-session'
    device.pending=Pending(1,'START','id','BASELINE')
    with pytest.raises(ProtocolError,match='ACK state mismatch'):
        device._accept(packet)


def test_unsolicited_ack_is_logged_without_reapplying_command():
    _,emulator,device=setup_device()
    ack={**emulator._common('ack'),**emulator.context(),'request_id':999,'accepted':True}
    device._accept(ack)
    packets=list(device.incoming.queue)
    assert packets[-1]['reason']=='old_or_unsolicited_ack'


def test_sample_null_signed_scale_and_device_timing_contract():
    _,emulator,_=setup_device()
    packet=sample(emulator)
    validate_sample(packet)
    packet['tgs2602_voltage_v']*=2
    with pytest.raises(ProtocolError,match='count/V'):
        validate_sample(packet)
    packet=sample(emulator)
    packet['tgs2602_adc_count']=-1; packet['tgs2602_voltage_v']=-.0001875
    validate_sample(packet)
    packet['tgs2602_adc_count']=32767; packet['tgs2602_voltage_v']=32767*.0001875
    packet['tgs2602_status']='ADC_LIMIT'; packet['tgs2602_valid']=False
    validate_sample(packet)
    packet['bme688_fresh']=False
    with pytest.raises(ProtocolError,match='Stale BME'):
        validate_sample(packet)


def test_begin_ticket_and_session_scopes_block_old_on_commands():
    emulator=EmulatedTransport(FakeClock())
    first=f'@1 {emulator.boot_id} session-one BEGIN {emulator.begin_ticket}\n'.encode()
    emulator.write(first)
    assert emulator.state.pwm==80
    emulator.write(f'@2 {emulator.boot_id} session-one OFF\n'.encode())
    assert emulator.state.pwm==0
    emulator.write(first)  # Cached ACK cannot replay an ON effect.
    assert emulator.state.pwm==0
    emulator.write(b'HELLO\n')
    second=f'@1 {emulator.boot_id} session-two BEGIN {emulator.begin_ticket}\n'.encode()
    emulator.write(second)
    assert emulator.state.pwm==80 and emulator.state.pump_start_count==2
    emulator.write(f'@3 {emulator.boot_id} session-one START 00000000-0000-0000-0000-000000000001\n'.encode())
    assert emulator.state.trial_count==0
    emulator.write(f'@4 {emulator.boot_id} session-two OFF\n'.encode())
    emulator.write(first)
    assert emulator.state.pwm==0


@pytest.mark.parametrize('session_id',['',None])
def test_active_samples_cannot_use_preflight_or_missing_session(session_id):
    _,emulator,device=setup_device()
    emulator.state.start_session(0)
    packet=sample(emulator)
    packet['session_id']=session_id
    with pytest.raises(ProtocolError,match='session'):
        device._accept(packet)
    assert device.last_seq==0


@pytest.mark.parametrize('field',['barrier_seq','applied_ms','reason'])
def test_correlated_ack_requires_effect_time_barrier_and_reason(field):
    _,emulator,device=setup_device()
    emulator.state.start_session(0)
    pending=Pending(1,'STATUS','',None)
    device.pending=pending
    packet={**emulator._common('ack'),**emulator.context(),'session_id':'host-session',
            'request_id':1,'accepted':True,'reason':'accepted','applied_ms':0,'barrier_seq':0}
    packet.pop(field)
    with pytest.raises(ProtocolError,match=field):
        device._accept(packet)
    assert not pending.done.is_set()


def test_blank_session_ack_cannot_complete_an_ordinary_request():
    _,emulator,device=setup_device()
    pending=Pending(1,'BEGIN','ticket','MONITOR')
    device.pending=pending
    packet={**emulator._common('ack'),**emulator.context(),
            'request_id':1,'accepted':False,'reason':'wrong_state','applied_ms':0,'barrier_seq':0}
    with pytest.raises(ProtocolError,match='Foreign session'):
        device._accept(packet)
    assert not pending.done.is_set()


def test_priority_off_can_confirm_idle_device_before_session_begin():
    _,emulator,device=setup_device()
    emulator.state.stop(0)
    device.off_pending=Pending(1,'OFF','',None)
    packet={**emulator._common('ack'),**emulator.context(),
            'request_id':1,'accepted':True,'reason':'commanded_off','applied_ms':0,'barrier_seq':0}
    device._accept(packet)
    assert device.off_acknowledged and device.off_pending.done.is_set()


def test_priority_fault_event_before_begin_does_not_block_its_ack():
    _,emulator,device=setup_device()
    emulator.state.stop(0,fault='test_fault')
    device.off_pending=Pending(1,'FAULT','',None)
    event={**emulator._common('event'),**emulator.context(),'event':'phase_change',
           'previous_phase':'OFF','previous_trial_id':None,'effective_ms':0,'processed_ms':0,'barrier_seq':0}
    device._accept(event)
    ack={**emulator._common('ack'),**emulator.context(),
         'request_id':1,'accepted':True,'reason':'commanded_off','applied_ms':0,'barrier_seq':0}
    device._accept(ack)
    assert device.off_acknowledged and device.off_pending.done.is_set()
