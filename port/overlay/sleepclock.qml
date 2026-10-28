// Palma 2 sleep screen: big clock, black on white, redrawn once a minute (palma-sleep keeps the SoC asleep in between).
import QtQuick
import QtQuick.Window

Window {
    id: win
    visibility: Window.FullScreen
    color: "white"
    title: "palma-sleep-clock"
    property date now: new Date()
    Timer { interval: 1000; running: true; repeat: true; onTriggered: if (new Date().getMinutes() !== win.now.getMinutes()) win.now = new Date() }
    Column {
        anchors.centerIn: parent
        spacing: 24
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatTime(win.now, "HH:mm")
            font.pixelSize: win.width * 0.36; font.weight: Font.Bold; color: "black"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.formatDate(win.now, "dddd, d MMMM")
            font.pixelSize: win.width * 0.07; font.weight: Font.DemiBold; color: "black"
        }
    }
}
