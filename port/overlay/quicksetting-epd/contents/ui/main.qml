// Tap cycles the e-ink refresh profile hd -> balanced -> fast -> ultra (/usr/local/bin/palma-epd via sudo).
import QtQuick
import org.kde.plasma.private.mobileshell.quicksettingsplugin as QS
import org.kde.plasma.plasma5support as P5Support

QS.QuickSetting {
    id: root
    property string profile: ""
    readonly property var names: ({ hd: "HD", balanced: "Сбалансированный", fast: "Быстрый", ultra: "Ультра" })

    text: "Режим экрана"
    icon: "view-refresh"
    status: names[profile] || profile
    enabled: profile === "fast" || profile === "ultra"

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => {
            const p = String(data["stdout"]).trim();
            if (p) root.profile = p;
            disconnectSource(source);
        }
    }
    Component.onCompleted: exec.connectSource("sudo -n /usr/local/bin/palma-epd")
    function toggle() { exec.connectSource("sudo -n /usr/local/bin/palma-epd next #" + Date.now()) }
}
