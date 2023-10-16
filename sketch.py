import itertools
from copy import deepcopy
import ezui
import merz
from mojo.subscriber import Subscriber, registerRoboFontSubscriber
from mojo.UI import splitText
from mojo.UI import appearanceColorKey, getDefault
from fontTools.pens.transformPen import TransformPen
from fontParts.world import RGlyph
from fontParts.base.base import interpolate

randomModeFrameDurations = dict(
    slow=2,
    normal=1,
    fast=0.5
)
smoothStepDistances = dict(
    slow=1/200,
    normal=1/100,
    fast=1/50
)

controlsFadeDuration = 0.3

controlButtonHeight = 40
controlBigButtonHeight = controlButtonHeight
controlBigButtonWidth = controlBigButtonHeight
controlSmallButtonHeight = controlButtonHeight
controlSmallButtonWidth = 30

bigSymbolConfiguration = dict(
    pointSize=controlBigButtonWidth * 0.75,
    colors=[(1, 1, 1, 1)],
    renderingMode="palette",
    weight="regular"
)
smallSymbolConfiguration = deepcopy(bigSymbolConfiguration)
smallSymbolConfiguration["pointSize"] = controlSmallButtonWidth * 0.5

controlPlayImage = ezui.makeImage(
    symbolName="play.fill",
    symbolConfiguration=bigSymbolConfiguration
)
controlPauseImage = ezui.makeImage(
    symbolName="pause.fill",
    symbolConfiguration=bigSymbolConfiguration
)
controlBackImage = ezui.makeImage(
    symbolName="backward.frame.fill",
    symbolConfiguration=smallSymbolConfiguration
)
controlForwardImage = ezui.makeImage(
    symbolName="forward.frame.fill",
    symbolConfiguration=smallSymbolConfiguration
)
controlSettingsImage = ezui.makeImage(
    symbolName="gearshape.fill",
    symbolConfiguration=smallSymbolConfiguration
)

storedLocationLimit = 5000


class LavaLampController(Subscriber, ezui.WindowController):

    debug = True

    def build(self):
        self.previewBackgroundColor = (1, 1, 1, 1)
        self.previewFillColor = (0, 0, 0, 1)
        self.previewProblemBackgroundColor = (0.8, 0, 0, 1)

        content = """
        * MerzView @preview
        """
        buttonSize = 30
        descriptionData = dict(
            preview=dict(
                backgroundColor=(1, 1, 1, 1),
                delegate=self
            ),
        )
        self.w = ezui.EZWindow(
            content=content,
            descriptionData=descriptionData,
            controller=self,
            size=(500, 500),
            minSize=(300, 300),
            margins=0,
            title="Lava Lamp"
        )
        self.preview = self.w.getItem("preview")
        self.previewContainer = self.preview.getMerzContainer()

        self.previewAnimator = self.previewContainer.appendStepAnimatorSublayer(
            ownerIdentifier="com.typesupply.LavaLamp",
            delegate=self,
            frameDuration=1,
            position=("left", "bottom"),
            # borderColor=(1, 0, 0, 0.5),
            # borderWidth=10,
            backgroundColor=self.previewBackgroundColor
        )
        self.previewPathContainer = self.previewAnimator.appendBaseSublayer(
            # borderColor=(0, 0, 1, 0.5),
            # borderWidth=8,
            # backgroundColor=(1, 1, 0, 0.5)
        )
        self.previewPathLayer = self.previewPathContainer.appendPathSublayer(
            position=("center", 0),
            fillColor=self.previewFillColor,
            # backgroundColor=(0, 1, 0, 0.25),
            # borderWidth=20,
            # borderColor=(1, 0, 0, 0.5)
        )
        self.previewLocationTextLayer = self.previewAnimator.appendTextLineSublayer(
            position=(
                dict(point="left", offset=10),
                dict(point="top", offset=-10),
            ),
            pointSize=12,
            figureStyle="tabular",
            fillColor=self.previewFillColor,
            backgroundColor=self.previewBackgroundColor,
            cornerRadius=5,
            padding=(10, 5),
            opacity=0
        )

        self.controlsContainer = self.previewContainer.appendBaseSublayer(
            position=("center", dict(point="bottom", offset=15)),
            size=(200, 50),
            cornerRadius=5,
            opacity=0,
            backgroundColor=(0, 0, 0, 0.5)
        )
        self.backFrameButton = self.controlsContainer.appendImageSublayer(
            name="backFrameButton",
            size=(controlSmallButtonWidth, controlSmallButtonHeight),
            position=(
                dict(point="center", offset=-controlSmallButtonWidth),
                "center"
            ),
            image=controlBackImage,
            alignment="center",
            acceptsHit=True
        )
        self.playButton = self.controlsContainer.appendImageSublayer(
            name="playButton",
            size=(controlBigButtonWidth, controlBigButtonHeight),
            position=("center", "center"),
            image=controlPlayImage,
            alignment="center",
            acceptsHit=True
        )
        self.forwardFrameButton = self.controlsContainer.appendImageSublayer(
            name="forwardFrameButton",
            size=(controlSmallButtonWidth, controlSmallButtonHeight),
            position=(
                dict(point="center", offset=controlSmallButtonWidth),
                "center"
            ),
            image=controlForwardImage,
            alignment="center",
            acceptsHit=True
        )
        self.settingsButton = self.controlsContainer.appendImageSublayer(
            name="settingsButton",
            size=(controlSmallButtonWidth, controlSmallButtonHeight),
            position=(
                dict(point="right", offset=-10),
                "center"
            ),
            image=controlSettingsImage,
            alignment="center",
            acceptsHit=True
        )

        self.mode = None
        self.speed = None
        self.text = ""
        self.glyphNamesFromText = []
        self.previousLocations = []
        self.currentLocation = None
        self.nextLocations = []
        self.animating = False
        self.setText("ABC")
        self.setMode("smooth", "normal")
        self.loadColors()

    def started(self):
        self.w.open()
        self.startAnimating()

    def destroy(self):
        self.stopAnimating()

    # Modes
    # -----

    def setMode(self, mode, speed):
        if (mode, speed) == (self.mode, self.speed):
            return
        self.mode = mode
        self.speed = speed
        self.rebuildAnimationData()

    def setText(self, text):
        self.text = text
        self._convertTextToGlyphNames()

    def _convertTextToGlyphNames(self):
        ds = CurrentDesignspace()
        if ds is None:
            self.glyphNamesFromText = []
            return
        currentGlyphName = None
        currentGlyph = CurrentGlyph()
        if currentGlyph is not None:
            currentGlyphName = currentGlyph.name
        rawGlyphNames = splitText(
            text=self.text,
            cmap=ds.getCharacterMapping()
        )
        glyphNames = []
        for glyphName in rawGlyphNames:
            if glyphName == "/?":
                if currentGlyphName is not None:
                    glyphNames.append(currentGlyphName)
            else:
                glyphNames.append(glyphName)
        self.glyphNamesFromText = glyphNames

    def _calculateSmoothSpaceEdges(self):
        ds = CurrentDesignspace()
        if ds is not None:
            spaceEdges = []
            for axisDescriptor in ds.axes:
                spaceEdges.append((
                    (axisDescriptor.name, axisDescriptor.minimum),
                    (axisDescriptor.name, axisDescriptor.maximum),
                ))
            self.smoothSpaceEdges = list(itertools.product(*spaceEdges))
            self.currentSmoothSpaceStartEdge = self.smoothSpaceEdges.pop(0)

    def calculateNewLocation(self, ds):
        if self.mode == "random":
            return self._calculateRandomLocation(ds)
        elif self.mode == "smooth":
            return self._calculateSmoothLocation(ds)

    def _calculateRandomLocation(self, ds):
        return ds.randomLocation()

    def _calculateSmoothLocation(self, ds):
        step = self.currentSmoothStep + self.smoothStepInterval
        if step >= 1.0:
            step = 0
            self.smoothSpaceEdges.append(self.currentSmoothSpaceStartEdge)
            self.currentSmoothSpaceStartEdge = self.smoothSpaceEdges.pop(0)
        startEdge = self.currentSmoothSpaceStartEdge
        nextEdge = self.smoothSpaceEdges[0]
        location = {}
        for i in range(len(startEdge)):
            tag, startValue = startEdge[i]
            tag, nextValue = nextEdge[i]
            location[tag] = interpolate(startValue, nextValue, step)
        self.currentSmoothStep = step
        return location

    # Animation
    # ---------

    def rebuildAnimationData(self):
        wasAnimating = self.animating
        if wasAnimating:
            self.stopAnimating()
        self.previousLocations.clear()
        self.currentLocation = None
        self.nextLocations.clear()
        if self.mode == "random":
            frameDuration = randomModeFrameDurations[self.speed]
        elif self.mode == "smooth":
            frameDuration = 1 / 30
            self.smoothStepInterval = smoothStepDistances[self.speed]
            self.currentSmoothStep = 0
            self._calculateSmoothSpaceEdges()
        self.previewAnimator.setFrameDuration(frameDuration)
        self._convertTextToGlyphNames()
        self.goForwardOneLocation()
        if wasAnimating:
            self.startAnimating()

    def startAnimating(self):
        self.animating = True
        self.playButton.setImage(controlPauseImage)
        self.previewLocationTextLayer.setOpacity(0)
        self.goForwardOneLocation()
        self.previewAnimator.startAnimation()

    def stopAnimating(self):
        self.animating = False
        self.playButton.setImage(controlPlayImage)
        self.previewAnimator.stopAnimation()
        self.previewLocationTextLayer.setOpacity(1.0)

    def goBackOneLocation(self):
        ds = CurrentDesignspace()
        location = None
        if ds is not None:
            if self.currentLocation is not None:
                self.nextLocations.append(self.currentLocation)
            if self.previousLocations:
                location = self.previousLocations.pop(-1)
        self.updatePathPreview(location)

    def goForwardOneLocation(self):
        ds = CurrentDesignspace()
        location = None
        if ds is not None:
            if self.currentLocation is not None:
                self.previousLocations.append(self.currentLocation)
                if len(self.previousLocations) > storedLocationLimit:
                    self.previousLocations = self.previousLocations[-storedLocationLimit:]
            if self.nextLocations:
                location = self.nextLocations.pop(-1)
            else:
                location = self.calculateNewLocation(ds)
        self.updatePathPreview(location)

    def updatePathPreview(self, location):
        ds = CurrentDesignspace()
        path = None
        scale = 1.0
        width = 0
        height = 0
        xPosition = 0
        yPosition = 0
        haveProblem = False
        if ds is None:
            self.previousLocations.clear()
            self.currentLocation = None
            self.nextLocations.clear()
        elif location is not None:
            if self.glyphNamesFromText:
                fontInfo = ds.makeFontProportions(location)
                unitsPerEm = fontInfo["unitsPerEm"]
                descender = fontInfo["descender"]
                height = unitsPerEm
                width = 0
                contentPen = merz.MerzPen()
                path = contentPen.path
                for glyphName in self.glyphNamesFromText:
                    pen = TransformPen(contentPen, (1, 0, 0, 1, width, 0))
                    glyph = ds.makeOneGlyph(glyphName, location)
                    if glyph is None:
                        haveProblem = True
                    else:
                        glyph.draw(pen)
                        width += glyph.width
                    viewHeight = self.preview.height()
                    viewWidth = self.preview.width()
                    buffer = viewHeight * 0.1
                    scale = (viewHeight * 0.8) / unitsPerEm
                    yPosition = buffer + (-descender * scale)
        self.previewPathContainer.addSublayerTransformation((scale, 0, 0, scale, xPosition, yPosition), name="upmScale")
        with self.previewPathLayer.propertyGroup():
            self.previewPathLayer.setPath(path)
            self.previewPathLayer.setSize((width, height))
        backgroundColor = self.previewBackgroundColor
        if haveProblem:
            backgroundColor = self.previewProblemBackgroundColor
        self.previewAnimator.setBackgroundColor(backgroundColor)
        self.currentLocation = location
        self.updateLocationText(location)

    def updateLocationText(self, location):
        locationText = ""
        if location is not None:
            locationText = []
            for k, v in sorted(location.items()):
                locationText.append(f"{k}: {v:.2f}")
            locationText = "\n".join(locationText)
        self.previewLocationTextLayer.setText(locationText)

    # StepAnimator Delegate
    # ---------------------

    def animationWillAdvance(self, sender):
        self.goForwardOneLocation()

    # MerzView Delegate
    # -----------------

    def acceptsFirstResponder(self, view):
        return True

    def sizeChanged(self, view):
        size = self.previewContainer.getSize()
        self.previewAnimator.setSize(size)
        self.previewPathContainer.setSize(size)

    def _getHitControl(self, event):
        event = merz.unpackEvent(event)
        location = event["location"]
        location = self.preview.convertWindowCoordinateToViewCoordinate(
            point=location
        )
        location = self.previewContainer.convertViewCoordinateToLayerCoordinate(
            location,
            self.previewContainer
        )
        hits = self.previewContainer.findSublayersContainingPoint(
            location,
            onlyAcceptsHit=True,
            ignoreLayers=[]
        )
        if hits:
            return hits[0]

    def mouseUp(self, view, event):
        hit = self._getHitControl(event)
        if not hit:
            return
        name = hit.getName()
        if name == "playButton":
            if self.animating:
                self.stopAnimating()
            else:
                self.startAnimating()
        elif name == "backFrameButton":
            self.stopAnimating()
            self.goBackOneLocation()
        elif name == "forwardFrameButton":
            self.stopAnimating()
            self.goForwardOneLocation()
        elif name == "settingsButton":
            SettingsPopUpController(
                parent=self.preview,
                callback=self.settingsPopUpCallback,
                settings=dict(
                    mode=self.mode,
                    speed=self.speed,
                    text=self.text
                )
            )

    def mouseEntered(self, view, event):
        with self.controlsContainer.propertyGroup(duration=controlsFadeDuration):
            self.controlsContainer.setOpacity(1.0)

    def mouseExited(self, view, event):
        with self.controlsContainer.propertyGroup(duration=controlsFadeDuration):
            self.controlsContainer.setOpacity(0)

    # Settings
    # --------

    def settingsPopUpCallback(self, settings):
        mode = settings["mode"]
        speed = settings["speed"]
        text = settings["text"]
        self.setText(text)
        self.setMode(mode, speed)

    def loadColors(self):
        self.previewFillColor = getDefault(appearanceColorKey("spaceCenterGlyphColor"))
        self.previewBackgroundColor = getDefault(appearanceColorKey("spaceCenterBackgroundColor"))
        self.previewAnimator.setBackgroundColor(self.previewBackgroundColor)
        self.previewPathLayer.setFillColor(self.previewFillColor)
        with self.previewLocationTextLayer.propertyGroup():
            r, g, b, a = self.previewBackgroundColor
            self.previewLocationTextLayer.setFillColor(self.previewFillColor)
            self.previewLocationTextLayer.setBackgroundColor((r, g, b, 0.75))

    # Subscriber
    # ----------

    def roboFontDidChangePreferences(self, info):
        self.loadColors()
        self.updatePathPreview(self.currentLocation)

    def roboFontAppearanceChanged(self, info):
        self.loadColors()
        self.updatePathPreview(self.currentLocation)

    def roboFontDidSwitchCurrentGlyph(self, info):
        self._convertTextToGlyphNames()
        self.updatePathPreview(self.currentLocation)

    # XXX
    # I'm not sure if:
    # 1. These are all that are needed.
    # 2. All of these are needed.

    def designspaceEditorDidOpenDesignspace(self, info):
        self.rebuildAnimationData()

    def designspaceEditorDidBecomeCurrent(self, info):
        self.rebuildAnimationData()

    def designspaceEditorAxisMapDidChange(self, info):
        self.rebuildAnimationData()

    def designspaceEditorAxesDidRemoveAxis(self, info):
        self.rebuildAnimationData()

    def designspaceEditorAxesDidAddAxis(self, info):
        self.rebuildAnimationData()

    def designspaceEditorAxesDidChange(self, info):
        self.rebuildAnimationData()

    def designspaceEditorSourcesDidRemoveSource(self, info):
        self.rebuildAnimationData()

    def designspaceEditorSourcesDidAddSource(self, info):
        self.rebuildAnimationData()


class SettingsPopUpController(ezui.WindowController):

    def build(self, parent, callback, settings):
        self.callback = callback

        self.modeOptions = {
            "Edge to Edge" : "smooth",
            "Random Locations" : "random"
        }
        modeSelected = 0
        for i, (k, v) in enumerate(self.modeOptions.items()):
            if v == settings["mode"]:
                modeSelected = i
                break

        self.speedOptions = {
            "Slow" : "slow",
            "Normal" : "normal",
            "Fast" : "fast"
        }
        speedSelected = 0
        for i, (k, v) in enumerate(self.speedOptions.items()):
            if v == settings["speed"]:
                speedSelected = i
                break

        text = settings["text"]

        content = """
        = TwoColumnForm

        : Mode:
        ( ...) @modePopUpButton

        : Speed:
        ( ...) @speedPopUpButton

        : Text:
        [_ _]  @speedTextField
        """
        descriptionData = dict(
            content=dict(
                titleColumnWidth=60,
                itemColumnWidth=150
            ),
            modePopUpButton=dict(
                items=self.modeOptions.keys(),
                selected=modeSelected
            ),
            speedPopUpButton=dict(
                items=self.speedOptions.keys(),
                selected=speedSelected
            ),
            speedTextField=dict(
                value=text
            )
        )
        self.w = ezui.EZPopUp(
            content=content,
            descriptionData=descriptionData,
            parent=parent,
            parentAlignmentPoint=("center", "center"),
            controller=self
        )

    def started(self):
        self.w.open()

    def contentCallback(self, sender):
        mode = self.w.getItemValue("modePopUpButton")
        mode = list(self.modeOptions.values())[mode]
        speed = self.w.getItemValue("speedPopUpButton")
        speed = list(self.speedOptions.values())[speed]
        text = self.w.getItemValue("speedTextField")
        settings = dict(
            mode=mode,
            speed=speed,
            text=text
        )
        self.callback(settings)


registerRoboFontSubscriber(LavaLampController)
