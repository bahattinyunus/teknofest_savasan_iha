import os
import sys
import numpy as np
import pytest

from core.models import KilitDurumu, EnergyState
from simulation.dogfight_simulator import TargetBehavior
from gcs.app import (
    PYQT_AVAILABLE,
    GCSMainWindow,
    PrimaryFlightDisplayWidget,
    LockCountdownRingWidget,
    TacticalRadarScopeWidget,
    EnergyEnvelopeChartWidget
)
from gcs.flight_viewer_3d import (
    Native3DFlightCanvas,
    FlightViewer3DWindow,
    generate_dogfight_trajectory
)


def test_python_3d_flight_canvas_projection_and_numpy_render():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if PYQT_AVAILABLE:
        from PyQt6.QtWidgets import QApplication
        _ = QApplication.instance() or QApplication(sys.argv)
    traj = generate_dogfight_trajectory(behavior=TargetBehavior.WEAVE, duration_s=8.0, dt=0.1)
    assert len(traj) == 80

    canvas = Native3DFlightCanvas()
    canvas.load_simulation_history(traj)
    canvas.current_frame_idx = 40

    proj = canvas.project_3d_to_2d((50.0, 20.0, -80.0), 960.0, 540.0)
    assert proj is not None
    assert 0.0 <= proj[0] <= 960.0
    assert 0.0 <= proj[1] <= 540.0

    img = canvas.render_to_numpy_image(width=640, height=360)
    assert img.shape == (360, 640, 3)
    assert int(np.max(img)) > 100


@pytest.mark.skipif(not PYQT_AVAILABLE, reason="PyQt6 kurulu degil")
def test_pyqt6_tactical_gcs_v4_custom_widgets():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    win = GCSMainWindow(system_controller=None)
    assert "v4.0" in win.windowTitle()

    # PFD, Kilit Halkası, Radar ve Boyd E-M güncellemelerini doğrula
    win.pfd_widget.set_flight_state(
        roll_deg=22.5,
        pitch_deg=8.0,
        yaw_deg=145.0,
        airspeed_mps=24.0,
        altitude_m=85.0,
        g_load=1.8,
        stall_warning=False
    )
    win.lock_ring_widget.set_lock_state(
        status=KilitDurumu.LOCKING,
        duration_s=2.6,
        total_locks=2,
        area_pct=6.4,
        mppi_prob=0.91
    )
    win.energy_chart.push_energy_state(
        EnergyState(
            ozgurluk_enerjisi_He_m=112.4,
            ozgurluk_fazla_gucu_Ps_mps=3.2,
            manevra_kose_hizi_Vc_mps=24.0,
            onerilen_taktik="RATE_FIGHT_2_CIRCLE"
        )
    )
    win.kilit_sayisi = 2
    win._current_lock_durum = KilitDurumu.LOCKING
    win._current_lock_sure = 2.6
    win.radar_widget.tick_sweep()
    win._trigger_tactical_action("MPPI_OPTIMAL_LOCK")
    win._update_ui_tick()

    assert win._active_tactical_mode == "MPPI_OPTIMAL_LOCK"
    assert win.lock_ring_widget.total_locks == 2
    win.close()
