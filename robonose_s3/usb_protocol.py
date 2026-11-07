"""Strict bounded dataset USB framing and validation, independent of pyserial/Qt."""
from dataclasses import dataclass
import json
import math
from .config import CHANNELS, LSB_V
from .schema import COLUMNS, DEVICES, SCHEMA

PROTOCOL="robonose.usb.v1"
FIRMWARE="3.0.0"
PROFILE_ID="s3_bringup_300_100_t2h2p4.v1"
CHANNEL_MAP=','.join(f'{key}={value}' for key,value in CHANNELS.items())
PHASES={"OFF","MONITOR","BASELINE","WAIT_EXPOSURE","EXPOSURE","WAIT_RECOVERY",
        "RECOVERY","WAIT_FINISH","WAIT_NAME","CLOSED","ERROR"}
SAMPLE_PHASES={"MONITOR","BASELINE","WAIT_EXPOSURE","EXPOSURE","WAIT_RECOVERY"}


class ProtocolError(RuntimeError):
    pass


def strict_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key]=value
    return result


class Framer:
    def __init__(self, limit=8192):
        self.limit=limit
        self.buffer=bytearray()
        self.discarding=False
        self.crash_dump=False

    def _parse_line(self,text):
        try:
            packet=json.loads(text,object_pairs_hook=strict_object,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'nonfinite: {value}')))
            if not isinstance(packet,dict):
                raise ValueError('JSON frame must be an object')
        except ValueError:
            for marker,reason in (('Guru Meditation Error:','mcu_panic'),
                                  ('Brownout detector was triggered','mcu_brownout'),
                                  ('assert failed:','mcu_assert'),
                                  ('CORRUPT HEAP:','mcu_heap_corruption')):
                position=text.find(marker)
                if position>=0:
                    self.crash_dump=True
                    return {'type':'device_fault','source':'usb_plain_text','reason':reason,
                            'detail':text[position:position+300]}
            if self.crash_dump:
                return None  # Full backtrace/ROM bytes remain lossless in wire.
            raise
        self.crash_dump=False
        return packet

    def feed(self, data):
        frames=[]
        for byte in data:
            if byte==10:
                if self.discarding:
                    frames.append({'type':'parser_event','reason':'oversized_frame'})
                elif self.buffer.strip():
                    try:
                        text=self.buffer.decode('utf-8').strip()
                        packet=self._parse_line(text)
                        if packet is not None:
                            frames.append(packet)
                    except (UnicodeError, ValueError) as error:
                        frames.append({'type':'parser_event','reason':'malformed_or_boot_chatter', 'detail':str(error)[:200]})
                self.buffer.clear(); self.discarding=False
            elif not self.discarding:
                if len(self.buffer)>=self.limit-1:
                    self.buffer.clear(); self.discarding=True
                else:
                    self.buffer.append(byte)
        return frames


def require(packet,key,expected):
    if packet.get(key)!=expected:
        raise ProtocolError(f'{key}: expected {expected!r}, received {packet.get(key)!r}')


def validate_hello(packet, initial=True):
    for key,value in {'protocol':PROTOCOL,'schema':SCHEMA,'firmware_version':FIRMWARE,
        'firmware_kind':'robonose_dataset_s3','channel_map':CHANNEL_MAP,'ads_fsr_v':6.144,
        'ads_lsb_v':LSB_V,'divider_factor':1,'ads_data_rate_sps':128,'ads_mode':'single_shot_single_ended',
        'ads_vdd_requested_v':5,'ads_address':72,'ads_sda':10,'ads_scl':11,'bme_sda':8,'bme_scl':9,
        'profile_id':PROFILE_ID,'heater_requested_c':300,'heater_requested_ms':100,
        'os_t_requested':2,'os_h_requested':2,'os_p_requested':4,'pump_pin':5,'valve_pin':4,
        'pump_pwm_hz':1000,'pump_pwm_bits':10,'valve_off_air_path':'FILTERED_AIR',
        'valve_on_air_path':'SAMPLE','sample_interval_ms':1000,'lease_ms':15000}.items():
        require(packet,key,value)
    if not isinstance(packet.get('boot_id'),str) or not packet['boot_id'] or not packet.get('device_id'):
        raise ProtocolError('Missing boot/device identity')
    if packet.get('bme_address') not in (0x77,0x76):
        raise ProtocolError('Unexpected BME address')
    if initial:
        if not isinstance(packet.get('begin_ticket'),str) or not packet['begin_ticket']:
            raise ProtocolError('Missing one-use BEGIN handshake ticket')
        if packet.get('phase') not in ('OFF','CLOSED') or packet.get('pump_pwm_pct')!=0 or packet.get('valve_energized') is not False:
            raise ProtocolError('Handshake must report commanded OFF/FILTERED_AIR')
        if packet.get('fault_latched'):
            raise ProtocolError('MCU fault latched; reset/readiness verification required')
    if packet.get('sensors_initialized'):
        for key,value in {'profile_readback_ok':True,'os_t_applied':2,'os_h_applied':2,
                          'os_p_applied':4,'heater_applied_ms':100}.items():
            require(packet,key,value)
    if (packet.get('firmware_revision')=='usb_irq_handoff.v3'
        and packet.get('serial_transport')=='idf_usb_serial_jtag'):
        for key,value in {'serial_ready':True,'serial_init_error':0,
                          'serial_irq_diagnostics_available':True,'serial_irq_owned_mask':12}.items():
            require(packet,key,value)
        for key in ('serial_irq_enabled_before','serial_irq_pending_before','serial_irq_enabled_after_init'):
            if type(packet.get(key)) is not int or not 0<=packet[key]<=0x7ffff:
                raise ProtocolError(f'Invalid USB IRQ diagnostic: {key}')
        enabled=packet['serial_irq_enabled_after_init']
        if enabled & ~12 or not enabled & 4:
            raise ProtocolError(f'Unsafe USB IRQ mask after handoff: {enabled:#x}; refusing BEGIN')
    return bool(packet.get('output_ready') and packet.get('sensors_initialized') and packet.get('profile_readback_ok'))


def validate_context(packet):
    phase=packet.get('phase')
    if phase not in PHASES:
        raise ProtocolError('Unknown phase')
    reason=packet.get('fault_reason')
    if reason is not None and (not isinstance(reason,str) or len(reason)>63):
        raise ProtocolError('Invalid MCU fault_reason')
    for key in ('context_epoch','segment_id','device_ms','phase_started_ms'):
        if type(packet.get(key)) is not int or packet[key]<0:
            raise ProtocolError(f'Invalid {key}')
    if packet.get('valve_energized') is not (phase in SAMPLE_PHASES):
        raise ProtocolError('Phase/valve mismatch')
    require(packet,'air_path_commanded','SAMPLE' if phase in SAMPLE_PHASES else 'FILTERED_AIR')
    require(packet,'pump_pwm_pct',0 if phase in ('OFF','CLOSED','ERROR') else 80)
    if packet.get('trial_id') is not None:
        import uuid
        try:
            uuid.UUID(packet['trial_id'])
        except (TypeError,ValueError,AttributeError):
            raise ProtocolError('Invalid trial UUID') from None
    if phase in ('BASELINE','EXPOSURE','RECOVERY'):
        if type(packet.get('deadline_ms')) is not int or packet['deadline_ms']<=packet['phase_started_ms']:
            raise ProtocolError('Timed phase lacks a valid MCU deadline')


def validate_sample(packet):
    validate_context(packet)
    for key in ('seq',):
        if type(packet.get(key)) is not int or packet[key]<1:
            raise ProtocolError(f'Invalid {key}')
    for key in ('mono_s','cycle_end_mono_s','phase_elapsed_s','schedule_lag_s'):
        if type(packet.get(key)) not in (int,float) or not math.isfinite(packet[key]) or packet[key]<0:
            raise ProtocolError(f'Invalid {key}')
    if packet['cycle_end_mono_s']<packet['mono_s']:
        raise ProtocolError('Negative scan duration')
    for sensor in DEVICES:
        for key in ('fresh','valid'):
            if type(packet.get(f'{sensor}_{key}')) is not bool:
                raise ProtocolError(f'Missing boolean {sensor}_{key}')
        for suffix in ('read_started_mono_s','read_duration_s'):
            value=packet.get(f'{sensor}_{suffix}')
            if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                raise ProtocolError(f'Invalid timing for {sensor}')
        if not isinstance(packet.get(f'{sensor}_status'),str) or f'{sensor}_error' not in packet:
            raise ProtocolError(f'Missing status/error for {sensor}')
    for sensor in CHANNELS.values():
        count=packet.get(f'{sensor}_adc_count'); volts=packet.get(f'{sensor}_voltage_v')
        if packet[f'{sensor}_valid'] or packet.get(f'{sensor}_status')=='ADC_LIMIT':
            if type(count) is not int or not -32768<=count<=32767 or type(volts) not in (int,float) or not math.isfinite(volts) or abs(volts-count*LSB_V)>1e-7:
                raise ProtocolError(f'{sensor}: count/V/LSB mismatch')
        elif count is not None or volts is not None:
            raise ProtocolError(f'{sensor}: invalid reading must be null')
    for key in ('gas_resistance_ohm','temperature_c','humidity_pct','pressure_hpa'):
        value=packet.get(key)
        if packet['bme688_fresh']:
            if type(value) not in (int,float) or not math.isfinite(value):
                raise ProtocolError(f'Invalid BME value: {key}')
        elif value is not None:
            raise ProtocolError('Stale BME values must be null')
    for key in ('new_data','gas_valid','heater_stable','context_straddled'):
        if type(packet.get(key)) is not bool:
            raise ProtocolError(f'Missing boolean {key}')
    require(packet,'profile_id',PROFILE_ID)


def validate_ack(packet):
    validate_context(packet)
    if type(packet.get('request_id')) is not int or not 0 < packet['request_id'] <= 0xffffffff:
        raise ProtocolError('ACK invalid request_id')
    if type(packet.get('accepted')) is not bool:
        raise ProtocolError('ACK missing accepted boolean')
    for key in ('applied_ms','barrier_seq'):
        if type(packet.get(key)) is not int or packet[key] < 0:
            raise ProtocolError(f'ACK invalid or missing {key}')
    if packet['applied_ms'] > packet['device_ms']:
        raise ProtocolError('ACK applied_ms is after its device_ms')
    if not isinstance(packet.get('reason'),str):
        raise ProtocolError('ACK missing reason')


@dataclass(frozen=True)
class SerialOptions:
    port: str
    kind: str
    baud: int=115200
    ack_timeout_s: float=.8
    retries: int=1
    receive_timeout_s: float=5
    handshake_timeout_s: float=8
    off_timeout_s: float=1.5

    def __post_init__(self):
        if not self.port or self.kind not in ('native-cdc','uart','emulated'):
            raise ValueError('Explicit port and native-cdc/uart mode are required')
        for value in (self.ack_timeout_s,self.receive_timeout_s,self.handshake_timeout_s,self.off_timeout_s):
            if not math.isfinite(value) or value<=0:
                raise ValueError('Timeout must be finite and positive')
