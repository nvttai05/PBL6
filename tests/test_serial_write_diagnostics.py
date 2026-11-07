import pytest

from robonose_s3.clock import FakeClock
from robonose_s3.serial_device import SerialDevice
from robonose_s3.usb_protocol import ProtocolError, SerialOptions


@pytest.mark.parametrize('accepted',[0,4])
def test_short_write_records_only_known_prefix_and_retains_attempt(accepted):
    records=[]
    device=SerialDevice(SerialOptions('MOCK','emulated'),'session',FakeClock(),records.append,lambda:False)
    class Transport:
        def write(self,data):
            return accepted
    packet=b'@1 boot session PING\n'
    with pytest.raises(ProtocolError,match='Short serial write on MOCK'):
        device._write(Transport(),packet)
    assert len(records)==1
    record=records[0]
    assert bytes.fromhex(record['bytes_hex'])==packet[:accepted]
    assert bytes.fromhex(record['attempted_bytes_hex'])==packet
    assert record['accepted_bytes']==accepted and record['requested_bytes']==len(packet)
    assert record['write_outcome']=='short_write'


def test_write_exception_is_not_misreported_as_zero_bytes_accepted():
    records=[]
    device=SerialDevice(SerialOptions('MOCK','emulated'),'session',FakeClock(),records.append,lambda:False)
    class Transport:
        def write(self,data):
            raise OSError('injected USB disconnect')
    with pytest.raises(OSError,match='USB disconnect'):
        device._write(Transport(),b'ALL_OFF\n',priority=True)
    assert records[0]['accepted_bytes'] is None
    assert records[0]['write_outcome']=='exception_or_unknown'
    assert bytes.fromhex(records[0]['attempted_bytes_hex'])==b'ALL_OFF\n'


def test_failed_persistence_cannot_mask_transport_fault_or_prevent_emergency_write():
    sent=[]
    def disk_failure(record):
        raise OSError('injected disk failure')
    device=SerialDevice(SerialOptions('MOCK','emulated'),'session',FakeClock(),disk_failure,lambda:False)
    class Transport:
        def write(self,data):
            sent.append(data)
            return 0
    with pytest.raises(ProtocolError,match='Short serial write'):
        device._write(Transport(),b'ALL_OFF\n',priority=True)
    assert sent==[b'ALL_OFF\n']


def test_successful_write_preserves_original_wire_record_contract():
    records=[]
    device=SerialDevice(SerialOptions('MOCK','emulated'),'session',FakeClock(),records.append,lambda:False)
    class Transport:
        def write(self,data):
            return len(data)
    device._write(Transport(),b'HELLO\n')
    assert records==[{'direction':'tx','host_mono_s':0,'bytes_hex':b'HELLO\n'.hex()}]
