// Tailscale toggle: tailscale up/down as the operator user (tailscale up --operator=user was run once as root).
import QtQuick
import org.kde.plasma.private.mobileshell.quicksettingsplugin as QS
import org.kde.plasma.plasma5support as P5Support

QS.QuickSetting {
    id: root
    property string state: ""
    property string ip: ""

    text: "Tailscale"
    icon: "network-vpn"
    enabled: state === "Running"
    status: state === "Running" ? (ip || "Вкл") : state === "NeedsLogin" ? "Нужен вход" : state ? "Выкл" : ""

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => {
            if (source.indexOf("status") >= 0) {
                try {
                    const s = JSON.parse(data["stdout"]);
                    root.state = s.BackendState || "";
                    root.ip = (s.Self && s.Self.TailscaleIPs && s.Self.TailscaleIPs[0]) || "";
                } catch (e) { root.state = "Stopped"; }
            } else {
                refresh.restart();
            }
            disconnectSource(source);
        }
    }
    Timer { id: refresh; interval: 1500; onTriggered: exec.connectSource("tailscale status --peers=false --json #" + Date.now()) }
    Timer { interval: 30000; running: true; repeat: true; onTriggered: refresh.restart() }
    Component.onCompleted: refresh.restart()
    function toggle() { exec.connectSource((enabled ? "tailscale down" : "tailscale up") + " #" + Date.now()) }
}
