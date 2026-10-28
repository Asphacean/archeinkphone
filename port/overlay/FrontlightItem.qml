// Palma 2 front light: brightness + colour temperature sliders for the action drawer (QuickSettings.qml).
// Drives /usr/local/bin/palma-light through sudo (sudoers.d/palma-contrast).
import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.components 3.0 as PC3
import org.kde.plasma.plasma5support as P5Support

ColumnLayout {
    id: root
    spacing: Kirigami.Units.smallSpacing

    P5Support.DataSource {
        id: exec
        engine: "executable"
        onNewData: (source, data) => {
            const v = String(data["stdout"]).trim().split(" ");
            if (v.length === 2 && !level.pressed && !temp.pressed) {
                level.value = parseInt(v[0]);
                temp.value = parseInt(v[1]);
            }
            disconnectSource(source);
        }
    }
    function apply() {
        exec.connectSource("sudo -n /usr/local/bin/palma-light " + Math.round(level.value) + " " + Math.round(temp.value) + " #" + Date.now());
    }
    Component.onCompleted: exec.connectSource("sudo -n /usr/local/bin/palma-light")

    Timer { id: throttle; interval: 150; onTriggered: root.apply() }

    RowLayout {
        Kirigami.Icon { source: "low-brightness"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; Layout.preferredHeight: width }
        PC3.Slider { id: level; Layout.fillWidth: true; from: 0; to: 100; stepSize: 1; onMoved: throttle.restart(); onPressedChanged: if (!pressed) root.apply() }
        Kirigami.Icon { source: "high-brightness"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; Layout.preferredHeight: width }
    }
    RowLayout {
        PC3.Label { text: "❄"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; horizontalAlignment: Text.AlignHCenter }
        PC3.Slider { id: temp; Layout.fillWidth: true; from: 0; to: 100; stepSize: 1; onMoved: throttle.restart(); onPressedChanged: if (!pressed) root.apply() }
        PC3.Label { text: "☀"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; horizontalAlignment: Text.AlignHCenter }
    }
}
