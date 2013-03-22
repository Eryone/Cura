from __future__ import absolute_import

import wx
import numpy
import time

import OpenGL
OpenGL.ERROR_CHECKING = False
from OpenGL.GLU import *
from OpenGL.GL import *

from Cura.util import profile
from Cura.util import meshLoader
from Cura.gui.util import opengl
from Cura.gui.util import openglGui

class anim(object):
	def __init__(self, start, end, runTime):
		self._start = start.copy()
		self._end = end.copy()
		self._startTime = time.time()
		self._runTime = runTime

	def isDone(self):
		return time.time() > self._startTime + self._runTime

	def getPosition(self):
		if self.isDone():
			return self._end
		f = (time.time() - self._startTime) / self._runTime
		ts=f*f
		tc=f*f*f
		f = 6*tc*ts + -15*ts*ts + 10*tc
		return self._start + (self._end - self._start) * f

class SceneView(openglGui.glGuiPanel):
	def __init__(self, parent):
		super(SceneView, self).__init__(parent)

		self._yaw = 30
		self._pitch = 60
		self._zoom = 300
		self._objectList = []
		self._objectShader = None
		self._focusObj = None
		self._selectedObj = None
		self._objColors = [None,None,None,None]
		self._mouseX = -1
		self._mouseY = -1
		self._viewTarget = numpy.array([0,0,0], numpy.float32);
		self._animView = None
		wx.EVT_IDLE(self, self.OnIdle)
		self.updateProfileToControls()

	def OnIdle(self, e):
		if self._animView is not None:
			self.Refresh()

	def loadScene(self, fileList):
		for filename in fileList:
			for obj in meshLoader.loadMeshes(filename):
				self._objectList.append(obj)

	def _deleteObject(self, obj):
		if obj == self._selectedObj:
			self._selectedObj = None
		if obj == self._focusObj:
			self._focusObj = None
		self._objectList.remove(obj)
		for m in obj._meshList:
			if m.vbo is not None:
				self.glReleaseList.append(m.vbo)

	def updateProfileToControls(self):
		self._machineSize = numpy.array([profile.getPreferenceFloat('machine_width'), profile.getPreferenceFloat('machine_depth'), profile.getPreferenceFloat('machine_height')])
		self._objColors[0] = profile.getPreferenceColour('model_colour')
		self._objColors[1] = profile.getPreferenceColour('model_colour2')
		self._objColors[2] = profile.getPreferenceColour('model_colour3')
		self._objColors[3] = profile.getPreferenceColour('model_colour4')

	def OnKeyChar(self, keyCode):
		if keyCode == wx.WXK_DELETE or keyCode == wx.WXK_NUMPAD_DELETE:
			if self._selectedObj is not None:
				self._deleteObject(self._selectedObj)
				self.Refresh()

	def OnMouseDown(self,e):
		self._mouseX = e.GetX()
		self._mouseY = e.GetY()
		if self._focusObj is not None:
			self._selectedObj = self._focusObj
			newViewPos = (self._selectedObj.getMaximum() + self._selectedObj.getMinimum()) / 2
			self._animView = anim(self._viewTarget, newViewPos, 0.5)

	def OnMouseMotion(self,e):
		if e.Dragging() and e.LeftIsDown():
			self._yaw += e.GetX() - self._mouseX
			self._pitch -= e.GetY() - self._mouseY
			if self._pitch > 170:
				self._pitch = 170
			if self._pitch < 10:
				self._pitch = 10
		if e.Dragging() and e.RightIsDown():
			self._zoom += e.GetY() - self._mouseY
			if self._zoom < 1:
				self._zoom = 1
			if self._zoom > numpy.max(self._machineSize) * 3:
				self._zoom = numpy.max(self._machineSize) * 3
		self._mouseX = e.GetX()
		self._mouseY = e.GetY()

	def _init3DView(self):
		# set viewing projection
		size = self.GetSize()
		glViewport(0, 0, size.GetWidth(), size.GetHeight())
		glLoadIdentity()

		glLightfv(GL_LIGHT0, GL_POSITION, [0.2, 0.2, 1.0, 0.0])

		glDisable(GL_RESCALE_NORMAL)
		glDisable(GL_LIGHTING)
		glDisable(GL_LIGHT0)
		glEnable(GL_DEPTH_TEST)
		glDisable(GL_CULL_FACE)
		glDisable(GL_BLEND)
		glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

		glClearColor(0.8, 0.8, 0.8, 1.0)
		glClearStencil(0)
		glClearDepth(1.0)

		glMatrixMode(GL_PROJECTION)
		glLoadIdentity()
		aspect = float(size.GetWidth()) / float(size.GetHeight())
		gluPerspective(45.0, aspect, 1.0, 1000.0)

		glMatrixMode(GL_MODELVIEW)
		glLoadIdentity()
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)

	def OnPaint(self,e):
		if self._animView is not None:
			self._viewTarget = self._animView.getPosition()
			if self._animView.isDone():
				self._animView = None
		if self._objectShader is None:
			self._objectShader = opengl.GLShader("""
uniform float cameraDistance;
varying float light_amount;

void main(void)
{
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
    gl_FrontColor = gl_Color;

	light_amount = abs(dot(normalize(gl_NormalMatrix * gl_Normal), normalize(gl_LightSource[0].position.xyz)));
	light_amount *= 1 - (length(gl_Position.xyz - vec3(0,0,cameraDistance)) / 1.5 / cameraDistance);
	light_amount += 0.2;
}
			""","""
uniform float cameraDistance;
varying float light_amount;

void main(void)
{
	gl_FragColor = vec4(gl_Color.xyz * light_amount, gl_Color[3]);
}
			""")
		self._init3DView()
		glTranslate(0,0,-self._zoom)
		glRotate(-self._pitch, 1,0,0)
		glRotate(self._yaw, 0,0,1)
		glTranslate(-self._viewTarget[0],-self._viewTarget[1],-self._viewTarget[2])
		glClearColor(1,1,1,1)
		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)

		for n in xrange(0, len(self._objectList)):
			obj = self._objectList[n]
			glColor4ub((n >> 24) & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF)
			self._renderObject(obj)

		if self._mouseX > -1:
			n = glReadPixels(self._mouseX, self.GetSize().GetHeight() - 1 - self._mouseY, 1, 1, GL_RGBA, GL_UNSIGNED_INT_8_8_8_8)[0][0]
			if n < len(self._objectList):
				self._focusObj = self._objectList[n]
			else:
				self._focusObj = None

		self._init3DView()
		glTranslate(0,0,-self._zoom)
		glRotate(-self._pitch, 1,0,0)
		glRotate(self._yaw, 0,0,1)
		glTranslate(-self._viewTarget[0],-self._viewTarget[1],-self._viewTarget[2])

		self._objectShader.bind()
		self._objectShader.setUniform('cameraDistance', self._zoom)
		for obj in self._objectList:
			col = self._objColors[0]
			if self._selectedObj == obj:
				col = map(lambda n: n * 1.5, col)
			elif self._focusObj == obj:
				col = map(lambda n: n * 1.2, col)
			elif self._focusObj is not None or  self._selectedObj is not None:
				col = map(lambda n: n * 0.8, col)
			glColor4f(col[0], col[1], col[2], col[3])
			self._renderObject(obj)
		self._objectShader.unbind()

		self._drawMachine()

	def _renderObject(self, obj):
		glPushMatrix()
		offset = obj.getDrawOffset()
		glTranslate(-offset[0], -offset[1], -offset[2])
		for m in obj._meshList:
			if m.vbo is None:
				m.vbo = opengl.GLVBO(m.vertexes, m.normal)
			m.vbo.render()
		glPopMatrix()

	def _drawMachine(self):
		size = [profile.getPreferenceFloat('machine_width'), profile.getPreferenceFloat('machine_depth'), profile.getPreferenceFloat('machine_height')]
		v0 = [ size[0] / 2, size[1] / 2, size[2]]
		v1 = [ size[0] / 2,-size[1] / 2, size[2]]
		v2 = [-size[0] / 2, size[1] / 2, size[2]]
		v3 = [-size[0] / 2,-size[1] / 2, size[2]]
		v4 = [ size[0] / 2, size[1] / 2, 0]
		v5 = [ size[0] / 2,-size[1] / 2, 0]
		v6 = [-size[0] / 2, size[1] / 2, 0]
		v7 = [-size[0] / 2,-size[1] / 2, 0]

		vList = [v0,v1,v3,v2, v1,v0,v4,v5, v2,v3,v7,v6, v0,v2,v6,v4, v3,v1,v5,v7]
		glEnable(GL_CULL_FACE)
		glEnable(GL_BLEND)
		glEnableClientState(GL_VERTEX_ARRAY)
		glVertexPointer(3, GL_FLOAT, 3*4, vList)

		glColor4ub(5, 171, 231, 64)
		glDrawArrays(GL_QUADS, 0, 4)
		glColor4ub(5, 171, 231, 96)
		glDrawArrays(GL_QUADS, 4, 8)
		glColor4ub(5, 171, 231, 128)
		glDrawArrays(GL_QUADS, 12, 8)

		sx = self._machineSize[0]
		sy = self._machineSize[1]
		for x in xrange(-int(sx/20)-1, int(sx / 20) + 1):
			for y in xrange(-int(sx/20)-1, int(sy / 20) + 1):
				x1 = x * 10
				x2 = x1 + 10
				y1 = y * 10
				y2 = y1 + 10
				x1 = max(min(x1, sx/2), -sx/2)
				y1 = max(min(y1, sy/2), -sy/2)
				x2 = max(min(x2, sx/2), -sx/2)
				y2 = max(min(y2, sy/2), -sy/2)
				if (x & 1) == (y & 1):
					glColor4ub(5, 171, 231, 127)
				else:
					glColor4ub(5 * 8 / 10, 171 * 8 / 10, 231 * 8 / 10, 128)
				glBegin(GL_QUADS)
				glVertex3f(x1, y1, -0.02)
				glVertex3f(x2, y1, -0.02)
				glVertex3f(x2, y2, -0.02)
				glVertex3f(x1, y2, -0.02)
				glEnd()

		glDisableClientState(GL_VERTEX_ARRAY)
		glDisable(GL_BLEND)
		glDisable(GL_CULL_FACE)
