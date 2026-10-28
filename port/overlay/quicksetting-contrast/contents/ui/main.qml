// Tap cycles the TCON contrast presets through /usr/local/bin/palma-contrast (sudo, see sudoers.d/palma-contrast).
import QtQuick
import org.kde.plasma.private.mobileshell.quicksettingsplugin as QS
import org.kde.plasma.plasma5support as P5Support

QS.QuickSetting {
    id: root
    property int level: -1
    readonly property var presets: [0, 32, 64, 128, 255]

    text: i18n("Contrast")
    icon: "contrast"
    status: level < 0 ? "" : String(level)
    enabled: level > 0

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => {
            const v = parseInt(data["stdout"]);
            if (!isNaN(v))
                root.level = v;
            disconnectSource(source);
        }
    }

    Component.onCompleted: exec.connectSource("sudo -n /usr/local/bin/palma-contrast")

    function toggle() {
        const next = presets.find(p => p > level);
        exec.connectSource("sudo -n /usr/local/bin/palma-contrast " + (next === undefined ? presets[0] : next));
    }
}
