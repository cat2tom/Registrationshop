"""
LandmarkTransformationTool (TransformationTool)

:Authors:
	Berend Klein Haneveld
"""
from TransformationTool import TransformationTool
from core.decorators import overrides
from ui.widgets.PointsWidget import PointsWidget
from ui.transformations import TwoStepPicker as Picker
from ui.transformations import Transformation
from ui.widgets.StatusWidget import StatusWidget
from vtk import vtkSphereSource
from vtk import vtkPolyDataMapper
from vtk import vtkActor
from vtk import vtkPoints
from vtk import vtkLandmarkTransform
from vtk import vtkRegularPolygonSource
from vtk import vtkTransform
from vtk import vtkMatrix4x4
from vtk import vtkProp3DFollower
from PySide.QtGui import QWidget
from PySide.QtGui import QGridLayout
from PySide.QtGui import QComboBox
from PySide.QtGui import QLabel
from PySide.QtCore import Signal
from PySide.QtCore import Slot
from PySide.QtCore import Qt


class LandmarkTransformationTool(TransformationTool):
	"""
	LandmarkTransformationTool
	"""
	updatedLandmarks = Signal(list, list)

	def __init__(self):
		super(LandmarkTransformationTool, self).__init__()

		self.fixedPicker = Picker()
		self.movingPicker = Picker()

		self.fixedPoints = []  # Locations
		self.movingPoints = []  # Locations

		self.landmarks = []  # All the landmark objects

		self.activeIndex = 0
		self.landmarkTransformType = 0  # Rigid

	@overrides(TransformationTool)
	def getParameterWidget(self):
		pointsWidget = PointsWidget()
		self.updatedLandmarks.connect(pointsWidget.setPoints)
		pointsWidget.activeLandmarkChanged.connect(self.setActiveLandmark)

		self.landmarkComboBox = QComboBox()
		self.landmarkComboBox.addItem("Rigid body")
		self.landmarkComboBox.addItem("Similarity")
		self.landmarkComboBox.addItem("Affine")
		self.landmarkComboBox.currentIndexChanged.connect(self.landmarkTypeChanged)

		layout = QGridLayout()
		layout.setAlignment(Qt.AlignTop)
		layout.addWidget(QLabel("Transform type"), 0, 0)
		layout.addWidget(self.landmarkComboBox, 0, 1)
		layout.addWidget(pointsWidget, 1, 0, 1, 2)

		widget = QWidget()
		widget.setLayout(layout)
		return widget

	@overrides(TransformationTool)
	def setRenderWidgets(self, fixed=None, moving=None, multi=None):
		self.fixedWidget = fixed
		self.movingWidget = moving
		self.multiWidget = multi

		self.fixedPicker.setWidget(self.fixedWidget)
		self.movingPicker.setWidget(self.movingWidget)

		self.fixedPicker.pickedLocation.connect(self.pickedFixedLocation)
		self.movingPicker.pickedLocation.connect(self.pickedMovingLocation)

		transform = Transformation(vtkTransform(), Transformation.TypeLandmark)
		self.multiWidget.transformations.append(transform)

		statusWidget = StatusWidget.Instance()
		statusWidget.setText("Place landmarks in both volumes to create a landmark transform. Hold your " +
			"mouse over a volume and press 'A'. Turn the volume, move your mouse and press 'A' again to set a " +
			"landmark.")

	def setLandmarkWidgets(self, fixed, moving):
		self.fixedLandmarkWidget = fixed
		self.movingLandmarkWidget = moving

		self.fixedPicker.setPropertiesWidget(self.fixedLandmarkWidget)
		self.movingPicker.setPropertiesWidget(self.movingLandmarkWidget)

	@overrides(TransformationTool)
	def cancelTransform(self):
		del self.multiWidget.transformations[-1]

	@overrides(TransformationTool)
	def applyTransform(self):
		pass

	@overrides(TransformationTool)
	def cleanUp(self):
		self.fixedPicker.cleanUp()
		self.movingPicker.cleanUp()

		for landmark in self.landmarks:
			landmark.cleanUp()

		self.fixedPoints = []
		self.movingPoints = []

		self.fixedPicker = Picker()
		self.movingPicker = Picker()
		
		# Make sure the transform is properly set in the moving render widget
		shearTrans = self.multiWidget.transformations.scalingTransform()
		self.movingWidget.volume.SetUserTransform(shearTrans)

		self.fixedWidget.render()
		self.movingWidget.render()
		self.multiWidget.render()

		self.fixedLandmarkWidget.setVisible(False)
		self.movingLandmarkWidget.setVisible(False)

		self.toolFinished.emit()

	@Slot(int)
	def setActiveLandmark(self, index):
		self.activeIndex = index
		self._update()
		self.fixedWidget.render()
		self.movingWidget.render()
		self.multiWidget.render()

	@Slot(int)
	def landmarkTypeChanged(self, value):
		self.landmarkTransformType = value
		self.updateTransform()
		self.multiWidget.render()

	def updateTransform(self):
		"""
		Update the landmark transform
		"""
		if len(self.fixedPoints) == 0 or len(self.movingPoints) == 0:
			return

		fixedPoints = vtkPoints()
		movingPoints = vtkPoints()
		numberOfSets = min(len(self.fixedPoints), len(self.movingPoints))
		fixedPoints.SetNumberOfPoints(numberOfSets)
		movingPoints.SetNumberOfPoints(numberOfSets)

		for index in range(numberOfSets):
			fixedPoint = self.fixedPoints[index]
			movingPoint = self.movingPoints[index]
			fixedPoints.SetPoint(index, fixedPoint)
			if len(self.multiWidget.transformations) > 1:
				# Get the second to last transform
				transform = self.multiWidget.transformations[-2].transform
				transPoint = transform.TransformPoint(movingPoint)
				movingPoints.SetPoint(index, transPoint)
			else:
				movingPoints.SetPoint(index, movingPoint)

		landmarkTransform = vtkLandmarkTransform()
		if self.landmarkTransformType == 0:
			landmarkTransform.SetModeToRigidBody()
		elif self.landmarkTransformType == 1:
			landmarkTransform.SetModeToSimilarity()
		elif self.landmarkTransformType == 2:
			landmarkTransform.SetModeToAffine()
		landmarkTransform.SetSourceLandmarks(fixedPoints)
		landmarkTransform.SetTargetLandmarks(movingPoints)
		landmarkTransform.Update()

		matrix = landmarkTransform.GetMatrix()

		transform = vtkTransform()
		transform.Identity()
		transform.SetMatrix(matrix)
		transform.Update()
		transform.Inverse()
		
		self.multiWidget.transformations[-1] = Transformation(transform, Transformation.TypeLandmark)
		shearTrans = self.multiWidget.transformations.scalingTransform()
		self.movingWidget.volume.SetUserTransform(shearTrans)
		self._updateLandmarksTransform()
		self.movingWidget.render()

	def _updateLandmarksTransform(self):
		for landmark in self.landmarks:
			if landmark.flag == "moving" and landmark.renderer == self.multiWidget.renderer:
				transform = self.multiWidget.transformations.completeTransform()
				pos = self.movingPoints[landmark.id][:]
				pos = transform.TransformPoint(pos)
				landmark.setPosition(pos)
			elif landmark.flag == "moving" and landmark.renderer == self.movingWidget.renderer:
				pos = self.movingPoints[landmark.id][:]
				transform = self.multiWidget.transformations.scalingTransform()
				pos = transform.TransformPoint(pos)
				landmark.setPosition(pos)

	def pickedFixedLocation(self, location):
		"""
		Place spheres in fixed widget and in multi-widget
		"""
		# Do not transform location as it is in data coordinates already
		if self.activeIndex >= len(self.fixedPoints):
			landmark = Landmark(index=self.activeIndex,
				renderer=self.fixedWidget.renderer,
				overlay=self.fixedWidget.rendererOverlay,
				flag="fixed")
			landmark.id = self.activeIndex
			landmark.setPosition(location)
			self.landmarks.append(landmark)
			self.fixedPoints.append(location)
			landmarkMulti = Landmark(index=self.activeIndex,
				renderer=self.multiWidget.renderer,
				overlay=self.multiWidget.rendererOverlay,
				flag="fixed")
			landmarkMulti.id = self.activeIndex
			landmarkMulti.setPosition(location)
			self.landmarks.append(landmarkMulti)
		else:
			landmarks = [x for x in self.landmarks if (x.id == self.activeIndex and x.flag == "fixed")]
			for landmark in landmarks:
				landmark.setPosition(location)
			self.fixedPoints[self.activeIndex] = location

		self.updateTransform()
		self.updatedLandmarks.emit(self.fixedPoints, self.movingPoints)
		self._update()
		self.multiWidget.render()

	def pickedMovingLocation(self, location):
		"""
		Place spheres in moving widget and in multi-widget
		Location is in world coordinates.
		"""
		matrix = vtkMatrix4x4()
		matrix.DeepCopy(self.movingWidget.volume.GetMatrix())
		matrix.Invert()
		pos = location[:]
		pos.append(0.0)
		pos = matrix.MultiplyPoint(pos)
		pos = pos[0:3]
		# pos is now in volume coordinates
		# But for the landmark transform we have to first apply the previous transform

		if self.activeIndex >= len(self.movingPoints):
			landmark = Landmark(index=self.activeIndex,
				renderer=self.movingWidget.renderer,
				overlay=self.movingWidget.rendererOverlay,
				flag="moving")
			landmark.setPosition(pos)
			self.landmarks.append(landmark)
			self.movingPoints.append(pos)
			landmarkMulti = Landmark(index=self.activeIndex,
				renderer=self.multiWidget.renderer,
				overlay=self.multiWidget.rendererOverlay,
				flag="moving")
			landmarkMulti.id = self.activeIndex
			landmarkMulti.setPosition(location)
			self.landmarks.append(landmarkMulti)
		else:
			landmarks = [x for x in self.landmarks if (x.id == self.activeIndex and x.flag == "moving")]
			for landmark in landmarks:
				landmark.setPosition(pos)
			self.movingPoints[self.activeIndex] = pos

		self.updateTransform()
		self.updatedLandmarks.emit(self.fixedPoints, self.movingPoints)
		self._update()
		self.multiWidget.render()

	def _update(self):
		for landmark in self.landmarks:
			landmark.active = landmark.id == self.activeIndex
			landmark.update()
		self._updateLandmarksTransform()


def CreateSphere():
	sphereSource = vtkSphereSource()
	sphereSource.SetRadius(20)
	sphereSource.SetThetaResolution(6)
	sphereSource.SetPhiResolution(6)

	sphereMapper = vtkPolyDataMapper()
	sphereMapper.SetInputConnection(sphereSource.GetOutputPort())

	sphere = vtkActor()
	sphere.PickableOff()
	sphere.SetMapper(sphereMapper)
	sphere.GetProperty().SetColor(1.0, 1.0, 0.6)

	return sphere


def CreateCircle():
	circleSource = vtkRegularPolygonSource()
	circleSource.SetNumberOfSides(30)
	circleSource.SetRadius(28)
	circleSource.SetGeneratePolygon(False)

	circleMapper = vtkPolyDataMapper()
	circleMapper.SetInputConnection(circleSource.GetOutputPort())

	circle = vtkActor()
	circle.PickableOff()
	circle.SetMapper(circleMapper)
	circle.GetProperty().SetColor(1.0, 0.5, 0.5)

	return circle


class Landmark(object):
	"""
	Landmark is a container for vtkProps for easier
	management of resources.

	1. Landmark(renderer, overlay, volume)
	2. set self.flag
	3. set self.active
	4. set self.id
	5. set position

	"""
	def __init__(self, index, renderer, overlay, flag="Fixed"):
		super(Landmark, self).__init__()

		self.renderer = renderer
		self.overlay = overlay
		self.flag = flag

		self.colorActive = [1.0, 0.5, 0.7]
		self.colorInactive = [1.0, 1.0, 0.6]

		self.position = [0.0, 0.0, 0.0]  # coordinates in volume
		self.active = True
		self.id = index

		self.landmark = CreateSphere()

		self.landmarkIndicator = CreateCircle()
		self.landmarkIndicator.GetProperty().SetLineWidth(2)
		self.landmarkIndicator.GetProperty().SetOpacity(0.7)

		self.landmarkFollower = vtkProp3DFollower()
		self.landmarkFollower.SetProp3D(self.landmarkIndicator)
		self.landmarkFollower.SetCamera(self.renderer.GetActiveCamera())

		self.renderer.AddViewProp(self.landmark)
		if self.overlay:
			self.overlay.AddViewProp(self.landmarkFollower)

	def cleanUp(self):
		self.renderer.RemoveViewProp(self.landmark)
		self.overlay.RemoveViewProp(self.landmarkFollower)

	def setPosition(self, position):
		self.position = position
		self.update()
	
	def update(self):
		# Update color for landmark and landmarkIndicator
		if self.active:
			color = self.colorActive
			opacity = 0.7
		else:
			color = self.colorInactive
			opacity = 0.4
		self.landmark.GetProperty().SetColor(color[0], color[1], color[2])
		self.landmarkIndicator.GetProperty().SetColor(color[0], color[1], color[2])
		self.landmarkIndicator.GetProperty().SetOpacity(opacity)

		# Update position of landmark and landmarkFollower
		self.landmark.SetPosition(self.position[0], self.position[1], self.position[2])
		self.landmarkFollower.SetPosition(self.position[0], self.position[1], self.position[2])
