import json
from pathlib import Path
import pytest

from robonose_s3.usb_protocol import Framer
from robonose_s3.usb_protocol import ProtocolError,validate_hello
from robonose_s3.emulator import EmulatedTransport
from robonose_s3.clock import FakeClock
from test_serial_session import make_session, ready

PANIC=b"Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).\r\n"
DUMP=(b'Core  1 register dump:\r\nPC: 0x42015d3a  A2: 0x00000200\r\n'
      b'Backtrace: 0x42015d37:0x3fc975e0\r\nRebooting...\r\n'
      b'ESP-ROM:esp32s3-20210327\r\n')


@pytest.mark.parametrize('chunk_size',[1,7,64,4096])
def test_split_panic_is_preserved_without_flooding_backtrace_events(chunk_size):
    framer=Framer(); output=[]
    data=PANIC+DUMP*100+b'{"type":"hello"}\n'
    for start in range(0,len(data),chunk_size):
        output.extend(framer.feed(data[start:start+chunk_size]))
    assert len(output)==2
    assert output[0]['type']=='device_fault' and output[0]['reason']=='mcu_panic'
    assert 'Interrupt wdt timeout on CPU1' in output[0]['detail']
    assert output[1]=={'type':'hello'}


@pytest.mark.parametrize('line,reason',[
    (b'Brownout detector was triggered\n','mcu_brownout'),
    (b'assert failed: usb driver\n','mcu_assert'),
    (b'CORRUPT HEAP: damaged block\n','mcu_heap_corruption')])
def test_fatal_console_text_gets_specific_reason(line,reason):
    assert Framer().feed(line)[0]['reason']==reason


def test_panic_after_truncated_json_is_detected_but_valid_json_text_is_not_faulted():
    assert Framer().feed(b'{"type":"sample",'+PANIC)[0]['reason']=='mcu_panic'
    packet={'type':'event','message':PANIC.decode().strip()}
    assert Framer().feed(json.dumps(packet).encode()+b'\n')==[packet]


def test_panic_faults_immediately_and_preserves_cause_in_session(tmp_path):
    session,transport=make_session(tmp_path)
    try:
        ready(session)
        transport.inject(PANIC+DUMP*100)
        assert session.finished.wait(4)
        assert 'MCU mcu_panic:' in session.engine.fault_reason
        assert 'Interrupt wdt timeout on CPU1' in session.engine.fault_reason
        assert 'ACK timeout' not in session.engine.fault_reason
        assert session.snapshot()['writer']['status']=='ERROR'
        assert session.snapshot()['off_confirmed'] and transport.state.pwm==0
        assert sum(b' BEGIN ' in packet for packet in transport.writes)==1
        events=(session.engine.recorder.path/'session/events.jsonl').read_text(encoding='utf-8')
        assert 'mcu_fault_text' in events
        wire=(session.engine.recorder.path/'session/wire.jsonl').read_text(encoding='utf-8')
        received=b''.join(bytes.fromhex(json.loads(line)['bytes_hex']) for line in wire.splitlines() if json.loads(line)['direction']=='rx')
        assert PANIC in received
    finally:
        session.request_stop('panic test cleanup'); session.finished.wait(4)


@pytest.mark.parametrize('enabled',[0,8,0x204,0x20c])
def test_v3_handshake_refuses_inherited_or_missing_rx_irqs(enabled):
    hello=EmulatedTransport(FakeClock()).hello()
    hello.update(firmware_revision='usb_irq_handoff.v3',serial_transport='idf_usb_serial_jtag',
        serial_ready=True,serial_init_error=0,serial_irq_diagnostics_available=True,
        serial_irq_owned_mask=12,serial_irq_enabled_before=0x20c,serial_irq_pending_before=0x20c,
        serial_irq_enabled_after_init=enabled)
    with pytest.raises(ProtocolError,match='Unsafe USB IRQ'):
        validate_hello(hello)
    hello['serial_irq_enabled_after_init']=4
    assert validate_hello(hello)
