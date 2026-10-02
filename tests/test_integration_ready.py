import csv
import json
import time
from types import SimpleNamespace
import pytest
from robonose.config import load, validate
from robonose.quality import assess, baseline_quality
from robonose.pump_test import run
from robonose.cli import parser
from robonose.readers import SimReader
from robonose.writer import RunWriter
from robonose.state import StateMachine
from tests.test_core import FakeDevice
from tests.test_session import Process, csv_rows

def samples(gas_slope=0, temp_slope=0, humidity_slope=0, temperature=26):
    return [dict(elapsed_s=t,gas_resistance_ohm=100000+t*gas_slope,
        temperature_c=temperature+t*temp_slope,humidity_pct=55+t*humidity_slope,
        bme_status="OK",bme_fresh=True,gas_valid=True,heater_stable=True,new_data=True)
        for t in range(31)]

def test_stability_not_just_heater_bit_and_thresholds():
    rows=samples(gas_slope=2000,temperature=39)
    q=assess(rows,now=30,live=True)
    assert q["stable"] is False and q["signals"]["gas_resistance_ohm"]["drifting"]
    assert q["advisories"] and all(r["heater_stable"] for r in rows)
    assert assess(samples(),now=30,live=True)["stable"] is True
    assert assess(samples(temp_slope=.02),now=30,live=True)["stable"] is False
    assert assess(samples(humidity_slope=.03),now=30,live=True)["stable"] is False
    cfg=load()["stability"] | {"gas_pct_per_min":200,"gas_range_pct":100}
    assert assess(rows,cfg,now=30,live=True)["stable"] is True

def test_quality_missing_stale_near_zero_partial():
    assert assess(samples()[:3],now=2,live=True)["stable"] is None
    assert assess(samples(),now=40,live=True)["stable"] is None
    zero=samples()
    for r in zero:r["gas_resistance_ohm"]=0
    assert assess(zero,now=30,live=True)["stable"] is None
    bad=samples()
    for r in bad:r["bme_status"]="ERROR"
    assert assess(bad,now=30,live=True)["stable"] is None
    assert baseline_quality(samples(),complete=False)["stable"] is None

@pytest.mark.parametrize("field,value", [("window_s",0),("min_samples",1),
    ("max_invalid_fraction",float("nan")),("min_window_fraction",2)])
def test_stability_config_validation(field,value):
    cfg=load()
    cfg["stability"][field]=value
    with pytest.raises(ValueError):validate(cfg)

@pytest.mark.parametrize("active_high",[True,False])
def test_pump_test_mock_off_on_off_and_audit(tmp_path,active_high):
    cfg=load()
    cfg["pump"].update(enabled=True,confirmed=True,active_high=active_high)
    made=[]
    def factory(**kwargs):
        device=FakeDevice(**kwargs);made.append(device);return device
    args=parser().parse_args(["pump-test","--hardware","--enable-pump","--seconds",".02","--output",str(tmp_path)])
    assert run(args,cfg,factory)==0
    assert made[0].kwargs=={"pin":17,"active_high":active_high,"initial_value":False}
    assert made[0].commands[-2:]==["OFF","CLOSE"] and "ON" in made[0].commands
    meta_path=next(tmp_path.glob("exploration/*/*/metadata.json"))
    meta=json.loads(meta_path.read_text())
    assert meta["status"]=="COMPLETE" and meta["kind"]=="pump_test"
    records=csv_rows(meta_path.parent/"raw.csv")
    assert records[0]["pump_command"]=="OFF" and records[-1]["pump_command"]=="OFF"
    assert any(r["pump_command"]=="ON" for r in records)
    assert all(r["gas_resistance_ohm"]=="" for r in records)
    events=csv_rows(meta_path.parent/"events.csv")
    commands=[json.loads(r["details_json"])["command"] for r in events if r["event"]=="pump_command"]
    assert commands==["OFF","ON","OFF","OFF"]

def test_pump_test_interrupt_keeps_files_and_off(tmp_path,monkeypatch):
    cfg=load();cfg["pump"].update(enabled=True,confirmed=True,active_high=True)
    made=[]
    def factory(**kw):
        d=FakeDevice(**kw);made.append(d);return d
    def interrupt(_):raise KeyboardInterrupt()
    monkeypatch.setattr("robonose.pump_test.time.sleep",interrupt)
    args=parser().parse_args(["pump-test","--hardware","--enable-pump","--output",str(tmp_path)])
    assert run(args,cfg,factory)==0
    assert made[0].commands[-2:]==["OFF","CLOSE"]
    p=next(tmp_path.glob("exploration/*/*/metadata.json"))
    assert json.loads(p.read_text())["status"]=="ABORTED"
    assert (p.parent/"raw.csv").stat().st_size>0 and (p.parent/"events.csv").stat().st_size>0

def test_pump_test_exception_keeps_files_and_off(tmp_path):
    cfg=load();cfg["pump"].update(enabled=True,confirmed=True,active_high=True)
    made=[]
    class Broken(FakeDevice):
        def on(self):raise OSError("TRIG mock failure")
    def factory(**kw):
        d=Broken(**kw);made.append(d);return d
    args=parser().parse_args(["pump-test","--hardware","--enable-pump","--output",str(tmp_path)])
    assert run(args,cfg,factory)==1
    assert made[0].commands[-2:]==["OFF","CLOSE"]
    p=next(tmp_path.glob("exploration/*/*/metadata.json"))
    assert json.loads(p.read_text())["status"]=="ERROR"

def test_adc_divider_metadata_and_same_conversion(tmp_path):
    cfg=load();cfg["hardware"]["mq135_divider_factor"]=2.0
    cfg["hardware"]["mq135_divider_description"]="Đã xác nhận 10 kΩ/10 kΩ"
    reader=SimReader(cfg)
    row=reader.read("MONITOR",reader.started)
    assert row["mq135_voltage_v"]==row["mq135_adc_count"]*4.096/32768
    assert row["mq135_ao_voltage_v"]==row["mq135_voltage_v"]*2
    assert row["mq3_ao_voltage_v"] is None
    w=RunWriter(tmp_path,"sim",cfg,reader.applied)
    assert w.meta["adc_inputs"]["mq135"]["divider_factor_confirmed"]
    assert not w.meta["adc_inputs"]["mq3"]["divider_factor_confirmed"]
    w.finish(StateMachine(w.start,{}),"COMPLETE",time.monotonic())

def test_eof_in_baseline_saves_unassessed_quality(tmp_path):
    app=Process(tmp_path,["--baseline","30"])
    try:
        app.wait("MONITOR |")
        app.send("start");app.wait("Pha BASELINE")
        time.sleep(.2)
        app.p.stdin.close()
        assert app.p.wait(timeout=40)==0,app.text()
        path,meta=app.runs()[0]
        assert meta["status"]=="ABORTED" and meta["end_reason"]=="stdin EOF"
        assert meta["baseline_started_without_stability"] is True
        assert meta["baseline_unstable"] is None
        assert json.loads((path/"summary.json").read_text())["measurement_quality"]["baseline"]["stable"] is None
        assert all((path/f).exists() for f in ("raw.csv","events.csv","metadata.json","summary.json","signals.png","normalized.png"))
    finally:
        if app.p.stdin.closed:
            app.f.close()
        else:app.close()

def test_sim_pump_test_never_calls_gpio_factory(tmp_path):
    cfg=load();cfg["pump"].update(enabled=True,confirmed=True,active_high=True)
    args=parser().parse_args(["pump-test","--sim","--seconds",".01","--output",str(tmp_path)])
    def forbidden(**kw):raise AssertionError("GPIO access in sim")
    assert run(args,cfg,forbidden)==0
    path=next(tmp_path.glob("simulation/*/*/raw.csv"))
    assert all(r["pump_command"]=="DISABLED" for r in csv_rows(path))

def test_missing_bme_entire_baseline_keeps_adc_and_null_stats(tmp_path):
    app=Process(tmp_path,["--sim-fail-every","1"])
    try:
        app.wait("MONITOR |");app.send("start");app.wait("Pha WAIT_EXPOSURE")
        app.send("expose");app.wait("Pha WAIT_RECOVERY")
        app.send("recover");app.wait("Pha WAIT_FINISH")
        app.send("finish");app.wait("Đặt tên:")
        app.send("skip");app.send("skip");app.send("quit")
        assert app.p.wait(timeout=40)==0,app.text()
        path,meta=app.runs()[0]
        assert meta["status"]=="COMPLETE" and meta["baseline_unstable"] is None
        summary=json.loads((path/"summary.json").read_text())
        assert summary["signals"]["gas_resistance_ohm"]["baseline"]["mean"] is None
        assert summary["signals"]["gas_resistance_ohm"]["exposure"] is None
        assert all(r["gas_resistance_ohm"]=="" and r["mq135_voltage_v"]!="" for r in csv_rows(path/"raw.csv"))
        assert summary["measurement_quality"]["baseline"]["stable"] is None
    finally:app.close()

def test_manual_pump_abort_records_off_in_session_and_run(tmp_path,monkeypatch):
    from robonose.session import Session
    from robonose.pump import Pump
    monkeypatch.setattr("robonose.session.analyze",lambda p:None)
    cfg=load();cfg["sample_hz"]=30
    args=parser().parse_args(["collect","--sim","--auto","--output",str(tmp_path)])
    cfg["pump"].update(enabled=True,confirmed=True,active_high=True)
    pump=Pump(cfg["pump"],"hardware",FakeDevice)
    class Scripted(Session):
        step=0
        def auto(self,now):
            if self.step==0:
                self.command("start");self.step=1
            elif self.step==1:
                self.command("pump on");self.on_at=now;self.step=2
            elif self.step==2 and now-self.on_at>.15:
                self.command("abort");self.step=3
            elif self.step==3:
                self.stopping=True
    session=Scripted(args,cfg,SimReader(cfg),pump)
    assert session.run_session()==0
    assert pump.device.commands[-2:]==["OFF","CLOSE"]
    for path in (session.pending.path,session.log.path):
        events=csv_rows(path/"events.csv")
        commands=[json.loads(r["details_json"]) for r in events if r["event"]=="pump_command"]
        assert any(e.get("command")=="ON" for e in commands)
        assert any(e.get("command")=="OFF" and e.get("reason")=="run end" for e in commands)
    assert any(r["pump_command"]=="ON" for r in csv_rows(session.pending.path/"raw.csv"))
    assert session.pending.meta["status"]=="ABORTED"


def test_pump_test_failed_off_reports_unknown(tmp_path):
    cfg=load();cfg["pump"].update(enabled=True,confirmed=True,active_high=True)
    class BrokenOff(FakeDevice):
        def off(self):
            super().off()
            raise OSError("OFF failed")
    args=parser().parse_args(["pump-test","--hardware","--enable-pump","--output",str(tmp_path)])
    assert run(args,cfg,BrokenOff)==1
    p=next(tmp_path.glob("exploration/*/*/metadata.json"))
    meta=json.loads(p.read_text())
    assert meta["status"]=="ERROR" and "OFF" in meta["end_reason"]
    assert csv_rows(p.parent/"raw.csv")[-1]["pump_command"]=="UNKNOWN"
    assert json.loads((p.parent/"summary.json").read_text())["physical_feedback"] is None
