// Home screen line: output of /usr/local/bin/palma-stats every 10 s. Plain black text, no animation.
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import QtQuick.Layouts
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    property string line: "…"
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground

    P5Support.DataSource {
        id: exec
        engine: "executable"
        interval: 10000
        connectedSources: ["/usr/local/bin/palma-stats"]
        onNewData: (source, data) => root.line = String(data["stdout"]).trim()
    }

    fullRepresentation: PC3.Label {
        text: root.line
        font.weight: Font.DemiBold
        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.1
        horizontalAlignment: Text.AlignHCenter
        Kirigami.Theme.inherit: false
        Kirigami.Theme.colorSet: Kirigami.Theme.Complementary   // white on the black home wallpaper
        Layout.minimumWidth: implicitWidth
        Layout.minimumHeight: implicitHeight
    }
}
