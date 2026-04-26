import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Widgets
import qs.Commons
import qs.Services.UI
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  property ShellScreen screen
  property string widgetId: ""
  property string section: ""
  property int sectionWidgetIndex: -1
  property int sectionWidgetsCount: 0

  property var pinnedWindow: ({
                                "pinned": false
                              })
  property var windowsById: ({})
  property var workspacesById: ({})

  readonly property var widgetMetadata: BarWidgetRegistry.widgetMetadata[widgetId] || {}
  readonly property string screenName: screen ? screen.name : ""
  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || "/tmp"
  readonly property string niriSocketPath: Quickshell.env("NIRI_SOCKET") || ""
  readonly property bool hasNiriSocket: niriSocketPath !== ""
  // Distinct code lets us hide the Niri-only widget without treating normal `niri msg` exits as socket absence.
  readonly property int missingNiriSocketExitCode: 66
  readonly property var niriProcessEnvironment: ({
                                                   "MISSING_NIRI_SOCKET_EXIT_CODE": String(missingNiriSocketExitCode)
                                                 })
  property bool niriBackendEnabled: hasNiriSocket
  readonly property string stateFilePath: runtimeDir + "/niri-pinned-window.json"
  readonly property var widgetSettings: {
    if (section && sectionWidgetIndex >= 0 && screenName) {
      var widgetsBySection = Settings.getBarWidgetsForScreen(screenName);
      if (widgetsBySection && widgetsBySection[section]) {
        var widgets = widgetsBySection[section];
        if (sectionWidgetIndex < widgets.length && widgets[sectionWidgetIndex]) {
          return widgets[sectionWidgetIndex];
        }
      }
    }
    return {};
  }

  readonly property bool showIcon: (widgetSettings.showIcon !== undefined) ? widgetSettings.showIcon : (widgetMetadata.showIcon || false)
  readonly property string hideMode: (widgetSettings.hideMode !== undefined) ? widgetSettings.hideMode : (widgetMetadata.hideMode || "hidden")
  readonly property string scrollingMode: (widgetSettings.scrollingMode !== undefined) ? widgetSettings.scrollingMode : (widgetMetadata.scrollingMode || "hover")
  readonly property real maxWidth: (widgetSettings.maxWidth !== undefined) ? widgetSettings.maxWidth : Math.max(widgetMetadata.maxWidth || 0, screen ? screen.width * 0.06 : 0)
  readonly property bool useFixedWidth: (widgetSettings.useFixedWidth !== undefined) ? widgetSettings.useFixedWidth : (widgetMetadata.useFixedWidth || false)
  readonly property bool colorizeIcons: (widgetSettings.colorizeIcons !== undefined) ? widgetSettings.colorizeIcons : (widgetMetadata.colorizeIcons || false)
  readonly property string textColorKey: (widgetSettings.textColor !== undefined) ? widgetSettings.textColor : (widgetMetadata.textColor || "none")

  readonly property color textColor: Color.resolveColorKey(textColorKey)
  readonly property string barPosition: Settings.getBarPositionForScreen(screenName)
  readonly property bool isVerticalBar: barPosition === "left" || barPosition === "right"
  readonly property real barHeight: Style.getBarHeightForScreen(screenName)
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screenName)
  readonly property real barFontSize: Style.getBarFontSizeForScreen(screenName)
  readonly property int iconSize: Style.toOdd(capsuleHeight * 0.75)
  readonly property int pinGlyphSize: Math.max(10, Math.round(iconSize * 0.65))
  readonly property int pinGlyphRotation: 0
  readonly property int verticalSize: Style.toOdd(capsuleHeight * 0.85)
  readonly property bool hasPinnedWindow: pinnedWindow.pinned === true
  readonly property bool shouldDisplayWidget: niriBackendEnabled && (hideMode !== "hidden" || hasPinnedWindow)
  readonly property bool shouldRenderWidget: niriBackendEnabled && ((hideMode !== "hidden" || hasPinnedWindow) || opacity > 0)
  readonly property string pinnedTitle: {
    if (!hasPinnedWindow)
      return "";
    const title = pinnedWindow.title || "";
    if (title !== "")
      return title;
    const appId = pinnedWindow.app_id || "";
    return appId !== "" ? appId : "Pinned Window";
  }

  implicitHeight: niriBackendEnabled ? (isVerticalBar ? (((!hasPinnedWindow) && hideMode === "hidden") ? 0 : verticalSize) : barHeight) : 0
  implicitWidth: niriBackendEnabled ? (isVerticalBar ? (((!hasPinnedWindow) && hideMode === "hidden") ? 0 : verticalSize) : (((!hasPinnedWindow) && hideMode === "hidden") ? 0 : dynamicWidth)) : 0

  visible: shouldRenderWidget
  opacity: (shouldDisplayWidget && (hideMode !== "transparent" || hasPinnedWindow)) ? 1.0 : 0.0

  Behavior on opacity {
    NumberAnimation {
      duration: Style.animationFast
      easing.type: Easing.OutCubic
    }
  }

  Behavior on implicitWidth {
    NumberAnimation {
      duration: Style.animationFast
      easing.type: Easing.OutCubic
    }
  }

  Behavior on implicitHeight {
    NumberAnimation {
      duration: Style.animationFast
      easing.type: Easing.OutCubic
    }
  }

  function launchPinnedWindow() {
    if (!niriBackendEnabled) {
      return;
    }
    Quickshell.execDetached([Quickshell.env("HOME") + "/.config/niri/bin/pinned-window.sh", "summon"]);
  }

  function clearPinnedWindow() {
    if (!niriBackendEnabled) {
      return;
    }
    Quickshell.execDetached([Quickshell.env("HOME") + "/.config/niri/bin/pinned-window.sh", "clear"]);
  }

  function applyPinnedState() {
    root.syncPinnedWindow();
  }

  function refreshNiriSnapshots() {
    if (!niriBackendEnabled) {
      return;
    }
    if (!windowsSnapshotProcess.running) {
      windowsSnapshotProcess.running = true;
    }
    if (!workspacesSnapshotProcess.running) {
      workspacesSnapshotProcess.running = true;
    }
  }

  function applyWindowsSnapshot(windows) {
    const nextWindowsById = {};
    for (let i = 0; i < windows.length; i++) {
      const windowData = windows[i];
      nextWindowsById[String(windowData.id)] = windowData;
    }
    root.windowsById = nextWindowsById;
    root.syncPinnedWindow();
  }

  function applyWorkspacesSnapshot(workspaces) {
    const nextWorkspacesById = {};
    for (let i = 0; i < workspaces.length; i++) {
      const workspaceData = workspaces[i];
      nextWorkspacesById[String(workspaceData.id)] = workspaceData;
    }
    root.workspacesById = nextWorkspacesById;
    root.syncPinnedWindow();
  }

  function applyWindowUpdate(windowData) {
    if (!windowData || windowData.id === undefined || windowData.id === null) {
      return;
    }

    const nextWindowsById = Object.assign({}, root.windowsById);
    nextWindowsById[String(windowData.id)] = windowData;
    root.windowsById = nextWindowsById;
    root.syncPinnedWindow();
  }

  function applyWindowClosed(windowId) {
    const closedId = String(windowId || "");
    if (closedId === "" || root.windowsById[closedId] === undefined) {
      return;
    }

    const nextWindowsById = Object.assign({}, root.windowsById);
    delete nextWindowsById[closedId];
    root.windowsById = nextWindowsById;
    root.syncPinnedWindow();
  }

  function handleWindowsSnapshotLine(line) {
    const snapshotLine = line.trim();
    if (snapshotLine === "") {
      return;
    }

    try {
      const windows = JSON.parse(snapshotLine);
      if (Array.isArray(windows)) {
        root.applyWindowsSnapshot(windows);
      }
    } catch (error) {
      Logger.w("PinnedWindow", "Failed to parse windows snapshot:", error);
    }
  }

  function handleWorkspacesSnapshotLine(line) {
    const snapshotLine = line.trim();
    if (snapshotLine === "") {
      return;
    }

    try {
      const workspaces = JSON.parse(snapshotLine);
      if (Array.isArray(workspaces)) {
        root.applyWorkspacesSnapshot(workspaces);
      }
    } catch (error) {
      Logger.w("PinnedWindow", "Failed to parse workspaces snapshot:", error);
    }
  }

  function syncPinnedWindow() {
    if (!niriBackendEnabled) {
      root.pinnedWindow = ({
                             "pinned": false
                           });
      return;
    }

    if (!stateAdapter.pinned || !stateAdapter.id) {
      root.pinnedWindow = ({
                             "pinned": false
                           });
      return;
    }

    const pinnedId = String(stateAdapter.id);
    const windowData = root.windowsById[pinnedId];
    if (!windowData) {
      root.pinnedWindow = ({
                             "pinned": false
                           });
      return;
    }

    const workspaceData = root.workspacesById[String(windowData.workspace_id)] || {};
    root.pinnedWindow = ({
                           "pinned": true,
                           "id": pinnedId,
                           "app_id": windowData.app_id || "",
                           "title": windowData.title || "",
                           "is_floating": windowData.is_floating === true,
                           "workspace_name": workspaceData.name || "",
                           "workspace_id": windowData.workspace_id !== undefined ? windowData.workspace_id : null
                         });
  }

  function handleProcessExit(exitCode) {
    if (exitCode === missingNiriSocketExitCode) {
      niriBackendEnabled = false;
      root.syncPinnedWindow();
    }
  }

  function handleEventLine(line) {
    const eventLine = line.trim();
    if (eventLine === "") {
      return;
    }

    try {
      const eventData = JSON.parse(eventLine);
      if (eventData.WindowsChanged && eventData.WindowsChanged.windows) {
        root.applyWindowsSnapshot(eventData.WindowsChanged.windows);
      }
      if (eventData.WindowOpenedOrChanged && eventData.WindowOpenedOrChanged.window) {
        root.applyWindowUpdate(eventData.WindowOpenedOrChanged.window);
      }
      if (eventData.WindowClosed && eventData.WindowClosed.id !== undefined) {
        root.applyWindowClosed(eventData.WindowClosed.id);
      }
      if (eventData.WorkspacesChanged && eventData.WorkspacesChanged.workspaces) {
        root.applyWorkspacesSnapshot(eventData.WorkspacesChanged.workspaces);
      }
    } catch (error) {
      Logger.w("PinnedWindow", "Failed to parse niri event:", error);
    }
  }

  function iconSource() {
    if (!hasPinnedWindow) {
      return ThemeIcons.iconFromName("pinned");
    }

    const appId = pinnedWindow.app_id || "";
    if (appId !== "") {
      const appIcon = ThemeIcons.iconForAppId(appId.toLowerCase());
      if (appIcon && appIcon !== "") {
        return appIcon;
      }
    }

    return ThemeIcons.iconFromName("pinned");
  }

  function tooltipText() {
    if (!hasPinnedWindow) {
      return "";
    }

    const lines = ["Pinned Window", pinnedTitle];
    const workspaceName = pinnedWindow.workspace_name || "";
    if (workspaceName !== "") {
      lines.push("Workspace: " + workspaceName);
    }
    return lines.join("\n");
  }

  function calculateContentWidth() {
    var contentWidth = 0;
    var margins = Style.margin2S;

    if (showIcon) {
      contentWidth += iconSize;
      contentWidth += Style.marginS;
    }

    if (hasPinnedWindow) {
      contentWidth += pinGlyphSize;
      contentWidth += Style.marginXS;
    }

    contentWidth += titleContainer.measuredWidth;
    contentWidth += Style.margin2XXS;
    contentWidth += margins;

    return Math.ceil(contentWidth);
  }

  readonly property real dynamicWidth: {
    if (useFixedWidth) {
      return maxWidth;
    }
    return Math.min(calculateContentWidth(), maxWidth);
  }

  FileView {
    id: stateFileView
    path: root.stateFilePath
    printErrors: false
    watchChanges: true

    adapter: JsonAdapter {
      id: stateAdapter
      property bool pinned: false
      property string id: ""
    }

    onLoaded: {
      root.applyPinnedState();
      root.refreshNiriSnapshots();
    }
    onFileChanged: stateFileView.reload()

    onLoadFailed: error => {
        if (error !== 2) {
          Logger.w("PinnedWindow", "Failed to load pin state:", error);
        }
        stateAdapter.pinned = false;
        stateAdapter.id = "";
        root.applyPinnedState();
    }
  }

  Process {
    id: windowsSnapshotProcess
    // Niri-only widget: a stale/missing IPC socket should exit quietly instead of logging `niri msg` errors.
    command: ["sh", "-c", 'test -S "$NIRI_SOCKET" || exit "$MISSING_NIRI_SOCKET_EXIT_CODE"; exec niri msg -j windows']
    environment: root.niriProcessEnvironment
    running: false
    stdout: SplitParser {
      onRead: line => root.handleWindowsSnapshotLine(line)
    }
    stderr: SplitParser {
      onRead: line => Logger.w("PinnedWindow", "windows snapshot:", line)
    }
    onExited: (exitCode, exitStatus) => root.handleProcessExit(exitCode)
  }

  Process {
    id: workspacesSnapshotProcess
    // Niri-only widget: a stale/missing IPC socket should exit quietly instead of logging `niri msg` errors.
    command: ["sh", "-c", 'test -S "$NIRI_SOCKET" || exit "$MISSING_NIRI_SOCKET_EXIT_CODE"; exec niri msg -j workspaces']
    environment: root.niriProcessEnvironment
    running: false
    stdout: SplitParser {
      onRead: line => root.handleWorkspacesSnapshotLine(line)
    }
    stderr: SplitParser {
      onRead: line => Logger.w("PinnedWindow", "workspaces snapshot:", line)
    }
    onExited: (exitCode, exitStatus) => root.handleProcessExit(exitCode)
  }

  Process {
    id: eventStreamProcess
    // Niri-only widget: a stale/missing IPC socket should exit quietly instead of logging `niri msg` errors.
    command: ["sh", "-c", 'test -S "$NIRI_SOCKET" || exit "$MISSING_NIRI_SOCKET_EXIT_CODE"; exec niri msg -j event-stream']
    environment: root.niriProcessEnvironment
    running: root.niriBackendEnabled
    stdout: SplitParser {
      onRead: line => root.handleEventLine(line)
    }
    stderr: SplitParser {
      onRead: line => Logger.w("PinnedWindow", line)
    }
    onExited: (exitCode, exitStatus) => root.handleProcessExit(exitCode)
  }

  Component.onCompleted: root.refreshNiriSnapshots()

  Rectangle {
    id: pinnedRect
    visible: root.visible
    x: isVerticalBar ? Style.pixelAlignCenter(parent.width, width) : 0
    y: isVerticalBar ? 0 : Style.pixelAlignCenter(parent.height, height)
    width: isVerticalBar ? ((!hasPinnedWindow) && hideMode === "hidden" ? 0 : verticalSize) : ((!hasPinnedWindow) && (hideMode === "hidden") ? 0 : dynamicWidth)
    height: isVerticalBar ? ((!hasPinnedWindow) && hideMode === "hidden" ? 0 : verticalSize) : capsuleHeight
    radius: Style.radiusM
    color: Style.capsuleColor
    border.color: Style.capsuleBorderColor
    border.width: Style.capsuleBorderWidth
    scale: hasPinnedWindow ? 1.0 : 0.985

    Behavior on width {
      NumberAnimation {
        duration: Style.animationFast
        easing.type: Easing.OutCubic
      }
    }

    Behavior on scale {
      NumberAnimation {
        duration: Style.animationFast
        easing.type: Easing.OutCubic
      }
    }

    Item {
      id: mainContainer
      anchors.fill: parent
      anchors.leftMargin: isVerticalBar ? 0 : Style.marginS
      anchors.rightMargin: isVerticalBar ? 0 : Style.marginS

      RowLayout {
        id: rowLayout
        height: iconSize
        y: Style.pixelAlignCenter(parent.height, height)
        spacing: Style.marginS
        visible: !isVerticalBar
        z: 1

        Item {
          Layout.preferredWidth: iconSize
          Layout.preferredHeight: iconSize
          Layout.alignment: Qt.AlignVCenter
          visible: showIcon

          IconImage {
            id: pinnedIcon
            anchors.fill: parent
            source: root.iconSource()
            asynchronous: true
            smooth: true
            visible: source !== ""

            layer.enabled: colorizeIcons
            layer.effect: ShaderEffect {
              property color targetColor: Settings.data.colorSchemes.darkMode ? Color.mOnSurface : Color.mSurfaceVariant
              property real colorizeMode: 0.0

              fragmentShader: Qt.resolvedUrl(Quickshell.shellDir + "/Shaders/qsb/appicon_colorize.frag.qsb")
            }
          }
        }

        NScrollText {
          id: titleContainer
          text: pinnedTitle
          Layout.alignment: Qt.AlignVCenter
          maxWidth: {
            var iconWidth = (showIcon && pinnedIcon.visible ? (iconSize + Style.marginS) : 0);
            var pinWidth = hasPinnedWindow ? (pinGlyphSize + Style.marginXS) : 0;
            var totalMargins = Style.margin2XXS;
            var availableWidth = mainContainer.width - iconWidth - pinWidth - totalMargins;
            return Math.max(20, availableWidth);
          }
          scrollMode: {
            if (scrollingMode === "always")
              return NScrollText.ScrollMode.Always;
            if (scrollingMode === "hover")
              return NScrollText.ScrollMode.Hover;
            return NScrollText.ScrollMode.Never;
          }
          forcedHover: mainMouseArea.containsMouse
          fadeExtent: 0.01

          NText {
            text: pinnedTitle
            pointSize: barFontSize
            applyUiScale: false
            font.weight: Style.fontWeightMedium
            color: root.textColor
          }
        }

        NIcon {
          Layout.alignment: Qt.AlignVCenter
          visible: hasPinnedWindow
          icon: "pinned"
          width: pinGlyphSize
          height: pinGlyphSize
          color: Color.mPrimary
          rotation: pinGlyphRotation
          transformOrigin: Item.Center
        }
      }

      Item {
        id: verticalLayout
        width: parent.width - Style.margin2M
        height: parent.height - Style.margin2M
        x: Style.pixelAlignCenter(parent.width, width)
        y: Style.pixelAlignCenter(parent.height, height)
        visible: isVerticalBar
        z: 1

        Item {
          width: root.iconSize
          height: width
          x: Style.pixelAlignCenter(parent.width, width)
          y: Style.pixelAlignCenter(parent.height, height)
          visible: hasPinnedWindow

          IconImage {
            anchors.fill: parent
            source: root.iconSource()
            asynchronous: true
            smooth: true
            visible: source !== ""
          }

          NIcon {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: -Style.marginXXS
            anchors.bottomMargin: -Style.marginXXS
            icon: "pinned"
            width: pinGlyphSize
            height: pinGlyphSize
            color: Color.mPrimary
            rotation: pinGlyphRotation
            transformOrigin: Item.Center
          }
        }
      }
    }
  }

  MouseArea {
    id: mainMouseArea
    anchors.fill: parent
    anchors.leftMargin: (!isVerticalBar && section === "left" && sectionWidgetIndex === 0) ? -Style.marginS : 0
    anchors.rightMargin: (!isVerticalBar && section === "right" && sectionWidgetIndex === sectionWidgetsCount - 1) ? -Style.marginS : 0
    anchors.topMargin: (isVerticalBar && section === "left" && sectionWidgetIndex === 0) ? -Style.marginM : 0
    anchors.bottomMargin: (isVerticalBar && section === "right" && sectionWidgetIndex === sectionWidgetsCount - 1) ? -Style.marginM : 0
    hoverEnabled: true
    cursorShape: hasPinnedWindow ? Qt.PointingHandCursor : Qt.ArrowCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton

    onEntered: {
      const text = root.tooltipText();
      if (text !== "") {
        TooltipService.show(root, text, BarService.getTooltipDirection(root.screen?.name));
      }
    }

    onExited: TooltipService.hide()

    onClicked: function (mouse) {
      if (mouse.button === Qt.LeftButton && hasPinnedWindow) {
        root.launchPinnedWindow();
        return;
      }
      if (mouse.button === Qt.RightButton && hasPinnedWindow) {
        TooltipService.hide();
        PanelService.showContextMenu(pinMenu, root, screen);
      }
    }
  }

  NPopupContextMenu {
    id: pinMenu
    model: [
      {
        "label": "Unpin Window",
        "action": "unpin",
        "icon": "pinned-off"
      },
    ]

    onTriggered: function (action) {
      pinMenu.close();
      PanelService.closeContextMenu(screen);
      if (action === "unpin") {
        root.clearPinnedWindow();
      }
    }
  }
}
