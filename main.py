#!/usr/bin/env python3

from __future__ import print_function
import sys, time, cv2, pymssql, numpy as np, pathlib, platform, json, os
from fsdk import FSDK
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer
from ctypes import c_char
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
from datetime import datetime

MACHINE_NAME = platform.uname()[1]
print(MACHINE_NAME)
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FSDK_FACE_TEMPLATE_SIZE = 1024 + 4*4
FONT_SIZE = 30
LICENSE_KEY = "LImcnZzkzw8RrawhS1F1kirLGcLBEC5xWkpNWBFXCnSiOYEzzcbTSJ0M5NqD7e6Ai7KCJi4g63nKFPVyxhRHq0vwGN/d+bqXummVuocUNIzUO6EWAhlMUv/dtztWSAMNzi0RjrZm0XOJzq0ukos9ZQT4L+aiGm1mKjDEKuPETBk="
# DB_SERVER = "VTNAPP1"
# DB_USER = "Face"
# DB_PASSWORD = "u3v*m@pN"
# DB_NAME = "FaceRecognition"0

DB_SERVER = "10.64.4.63"
DB_USER = "sa"
DB_PASSWORD = "123456"
DB_NAME = "FaceRecognition"
FACE_LIST = []
FACE_LIST_JSON = []
DIR_NAME = pathlib.Path().absolute()
print(DIR_NAME)
print(type(DIR_NAME))

DIR_NAME = os.path.dirname(os.path.abspath(__file__))
print(DIR_NAME)
print(type(DIR_NAME))

DATA_FILE_PATH = f"{DIR_NAME}/data.json"
FD_MARKS_FILE_PATH = f"{DIR_NAME}/fd_masks1.bin"
QUERY_FACE_LIST = f"SELECT [Code],[Fullname],[Template],[SimilarThreshold],[ID],[Group] FROM FaceList WHERE Code = '0972' ORDER BY CreatedDate DESC"
QUERY_DEVICE_LIST = f"SELECT [MachineName],[MachineTypeID],[Location],[Status],[SoftwareVersion],[LastestUpdateVersion],[LastestUpdateDB] FROM DeviceList WHERE MachineName='{MACHINE_NAME}'"
TIME_RELOAD_FACE_LIST = 15 * 60 * 1000
TIME_CHECK_SOFTWARE_UPDATE = 15 * 60 * 1000
START_TIME_LOAD_FACE_LIST = datetime.now()


# Innitialize and declare FSDK
print("Initializing FSDK... ", end='')
FSDK.ActivateLibrary(LICENSE_KEY)
FSDK.Initialize()
print("OK\nLicense info:", FSDK.GetLicenseInfo())

FSDK.SetFaceDetectionParameters(True, True, 512)
FSDK.SetFaceDetectionThreshold(5)
err = FSDK.SetParameters(f"FaceDetectionModel={FD_MARKS_FILE_PATH};TrimFacesWithUncertainFacialFeatures=false")
print(err)


class FaceProccess(object):
    def Go_Search_Face(facetemplate,facelist):
        smltmp = 0
        similarity = 0
        ress = ""
        for face in facelist:
            item = (c_char*FSDK_FACE_TEMPLATE_SIZE).from_buffer(bytearray(face[2]))
            smltmp = FSDK.MatchFaces(facetemplate, item)
            if smltmp > face[3]:
                if(similarity < smltmp):
                    similarity = smltmp
                    ress = f"{face[0]} - {face[1]}"

        return [similarity, f"{ress} - {similarity}"]
    
    def writeDataFile(self,facelist):
        # Write data into local json backup file
        if(len(facelist) > 0):
            FACE_LIST_JSON = []
            for f in facelist:
                lf = list(f)
                lf[2] = str(f[2], "latin1")
                FACE_LIST_JSON.append(lf)

            f = open(DATA_FILE_PATH, "w")
            json_string = json.dumps(FACE_LIST_JSON)
            f.write(json_string)
            f.close()

    def Load_Face_List(self):
        rsFaceList = []
        try:
            # Connect to server
            conn = pymssql.connect(server=f'{DB_SERVER}', user=f'{DB_USER}', password=f'{DB_PASSWORD}', database=f'{DB_NAME}')
            cursor = conn.cursor()
            cursor.execute(QUERY_FACE_LIST)
            for item in cursor:
                rsFaceList.append(item)

            self.writeDataFile(rsFaceList)
            print("Load data from Database.")
            return rsFaceList
        except Exception as ex:
            print(ex)
            print("Load data from local file.")
            # Load data from Json backup file before when disconnected to server
            with open(DATA_FILE_PATH, "r") as f:
                data = json.load(f)
                #print(type(data))
                for item in data:
                    item[2] = bytes(item[2], "latin1")
                    rsFaceList.append(item)
            return rsFaceList

    def compareTime(beginTime, endTime):
        rsTime = datetime.timestamp(endTime) - datetime.timestamp(beginTime)
        return rsTime


# Load face list form server or local data file
face_pro = FaceProccess()
FACE_LIST = face_pro.Load_Face_List()
print(len(FACE_LIST))


class Camera(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(np.ndarray)
    running = True

    def run(self):
        self.camera = cv2.VideoCapture(CAMERA_INDEX)
        #self.camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self.mirror = True
        self.scale = 45
        while self.running:
            _, frame = self.camera.read()
            if _:
                #if self.mirror:
                #    frame = cv2.flip(frame, 1)

                #get the webcam size
                height, width, channels = frame.shape

                #prepare the crop
                centerX,centerY=int(height/2),int(width/2)
                radiusX,radiusY= int(self.scale*height/100),int(self.scale*width/100)

                minX,maxX=centerX-radiusX,centerX+radiusX
                minY,maxY=centerY-radiusY,centerY+radiusY

                cropped = frame[minX:maxX, minY:maxY]
                resized_cropped = cv2.resize(cropped, (width, height)) 

                #self.progress.emit(frame)
                self.progress.emit(resized_cropped)
            
        self.camera.release()
        self.finished.emit()


class FaceSearch(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(str)
    filename = None
    running = True
    is_new = False

    def set_filename(self, filename):
        self.filename = filename
        self.is_new = True

    def send_frame(self, f):
        self.frame = f
        self.is_new = True

    def run(self):
        self.ll = 0
        self.tt = 0
        self.ww = 0
        self.hh = 0
        while self.running:
            try:
                if self.is_new:
                    height, width, channel = self.frame.shape
                    buffer = self.frame.tobytes()
                    img = FSDK.LoadImageFromBuffer(buffer, width, height, channel*width, FSDK.FSDK_IMAGE_COLOR_24BIT)

                    fp = FSDK.DetectFace(img)
                    face_template = FSDK.GetFaceTemplateInRegion(img, fp)

                    rs = FaceProccess.Go_Search_Face(face_template, FACE_LIST)
                    if float(rs[0]) > 0:
                        self.progress.emit(f"{rs[1]} - {width} - {height}")

                    self.is_new = False

                    self.ll = fp.xc - int(fp.w * 0.5)
                    self.tt = fp.yc - int(fp.w * 0.5)
                    self.ww = int(fp.w * 0.95)
                    self.hh = int(fp.w * 1.05)
            except:
                self.ll = 0
                self.tt = 0
                self.ww = 0
                self.hh = 0
                pass
        
            ui.face_pos.left = self.ll
            ui.face_pos.top = self.tt
            ui.face_pos.width = self.ww
            ui.face_pos.height = self.hh

        self.finished.emit()
        

class FacePos():
    width = 0
    height = 0
    left = 0
    top = 0

class Ui_Recognize(object):
    isPrint = True
    need_to_exit = False
    displayTime = datetime.now()
    fontsizeDisplayName = 20
    fontsizeDisplayTime = 30
    fontsizeDisplayDate = 14
    fontsizeDisplayMessage = 20

    # fontsizeDisplayName = 15
    # fontsizeDisplayTime = 25
    # fontsizeDisplayDate = 11
    # fontsizeDisplayMessage = 20
    def setupUi(self, Recognize):
        Recognize.setObjectName("Recognize")
        Recognize.resize(1024, 600)
        Recognize.setStyleSheet("background-color:#ffffff;")
        #Recognize.setWindowFlag(Qt.FramelessWindowHint)
        self.centralwidget = QtWidgets.QWidget(Recognize)
        self.centralwidget.setObjectName("centralwidget")
        self.graphicsView = QtWidgets.QGraphicsView(self.centralwidget)
        self.graphicsView.setGeometry(QtCore.QRect(0, 0, 640, 480))
        self.graphicsView.setObjectName("graphicsView")
        self.graphicsView.setStyleSheet("border:none;")
        self.graphicsView_Logo = QtWidgets.QGraphicsView(self.centralwidget)
        self.graphicsView_Logo.setGeometry(QtCore.QRect(670, 15, 330, 163))
        self.graphicsView_Logo.setObjectName("graphicsView_Logo")
        self.graphicsView_Logo.setStyleSheet(f"background-image:url('{DIR_NAME}/Spartronics-Stacked-TM-FullColor.png');border:none;")
        #self.lblWelcome = QtWidgets.QLabel(self.centralwidget)
        #self.lblWelcome.setGeometry(QtCore.QRect(670, 210, 330, 30))
        font = QtGui.QFont()
        font.setFamily("MS Shell Dlg 2")
        font.setPointSize(12)
        # self.lblWelcome.setFont(font)
        # self.lblWelcome.setAlignment(QtCore.Qt.AlignCenter)
        # self.lblWelcome.setObjectName("lblWelcome")
        # self.lblWelcome.setStyleSheet("color:#20386e")
        self.lblTime = QtWidgets.QLabel(self.centralwidget)
        self.lblTime.setGeometry(QtCore.QRect(715, 230, 231, 45))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayTime)
        font.setBold(True)
        font.setWeight(75)
        self.lblTime.setFont(font)
        self.lblTime.setAlignment(QtCore.Qt.AlignCenter)
        self.lblTime.setObjectName("lblTime")
        self.graphicsView_Bottom = QtWidgets.QGraphicsView(self.centralwidget)
        self.graphicsView_Bottom.setGeometry(QtCore.QRect(0, 480, 1024, 120))
        self.graphicsView_Bottom.setObjectName("graphicsView_Bottom")
        self.graphicsView_Bottom.setStyleSheet("background-color:#b2e5f9;border:none;")
        self.lblMessage = QtWidgets.QLabel(self.centralwidget)
        self.lblMessage.setGeometry(QtCore.QRect(674, 370, 321, 91))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayMessage)
        font.setStrikeOut(False)
        font.setKerning(True)
        self.lblMessage.setFont(font)
        self.lblMessage.setAlignment(QtCore.Qt.AlignHCenter|QtCore.Qt.AlignTop)
        self.lblMessage.setWordWrap(True)
        self.lblMessage.setObjectName("lblMessage")
        self.label_4 = QtWidgets.QLabel(self.centralwidget)
        self.label_4.setGeometry(QtCore.QRect(10, 520, 111, 45))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayName)
        self.label_4.setFont(font)
        self.label_4.setObjectName("label_4")
        self.label_4.setStyleSheet("background-color:transparent;")
        self.lblCode = QtWidgets.QLabel(self.centralwidget)
        self.lblCode.setGeometry(QtCore.QRect(112, 520, 211, 45))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayName)
        font.setBold(True)
        font.setWeight(75)
        self.lblCode.setFont(font)
        self.lblCode.setObjectName("lblCode")
        self.lblCode.setStyleSheet("background-color:transparent;")
        self.label_6 = QtWidgets.QLabel(self.centralwidget)
        self.label_6.setGeometry(QtCore.QRect(315, 520, 131, 45))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayName)
        self.label_6.setFont(font)
        self.label_6.setObjectName("label_6")
        self.label_6.setStyleSheet("background-color:transparent;")
        self.lblName = QtWidgets.QLabel(self.centralwidget)
        self.lblName.setGeometry(QtCore.QRect(430, 520, 581, 45))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayName)
        font.setBold(True)
        font.setWeight(75)
        self.lblName.setFont(font)
        self.lblName.setObjectName("lblName")
        self.lblName.setStyleSheet("background-color:transparent;")
        self.lblDate = QtWidgets.QLabel(self.centralwidget)
        self.lblDate.setGeometry(QtCore.QRect(707, 282, 251, 30))
        font = QtGui.QFont()
        font.setPointSize(self.fontsizeDisplayDate)
        self.lblDate.setFont(font)
        self.lblDate.setAlignment(QtCore.Qt.AlignCenter)
        self.lblDate.setObjectName("lblDate")
        Recognize.setCentralWidget(self.centralwidget)

        self.retranslateUi(Recognize)
        QtCore.QMetaObject.connectSlotsByName(Recognize)

        #Event
        #self.pushButton.clicked.connect(self.closeApp)
        self.face_pos = FacePos()

        # Set timer to reload from DB
        self._change_timer = QTimer()
        self._change_timer.setInterval(TIME_RELOAD_FACE_LIST)
        self._change_timer.timeout.connect(self.reloadFaceList)
        self._change_timer.start()

        self._change_timer1 = QTimer()
        self._change_timer1.setInterval(TIME_CHECK_SOFTWARE_UPDATE)
        self._change_timer1.setSingleShot(True)
        self._change_timer1.timeout.connect(self.updateVersion)
        self._change_timer1.start()

        ### run camera on other thread
        # create a QThread object
        self.thread = QThread()
        self.capture = Camera()
        self.capture.moveToThread(self.thread)
        self.thread.started.connect(self.capture.run)
        self.thread.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.capture.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.capture.progress.connect(self.stream)
        self.thread.start()

        self.thread1 = QThread()
        self.facesearch = FaceSearch()
        self.facesearch.moveToThread(self.thread1)
        self.thread1.started.connect(self.facesearch.run)
        self.thread.finished.connect(self.thread1.quit)
        self.thread.finished.connect(self.facesearch.deleteLater)
        self.thread.finished.connect(self.thread1.deleteLater)
        self.facesearch.progress.connect(self.rsFaceRecognition)
        self.thread1.start()

    def stream(self, frame):
        height, width, channel = frame.shape
        #print(f"{width} - {height} - {channel}")
        qimage = QImage(frame.data, width, height, channel*width, QImage.Format_RGB888).rgbSwapped()
        pixmap = QPixmap(qimage)
        #pixmap_resized = pixmap.scaled(675*1, 750*1, QtCore.Qt.KeepAspectRatio)
        #item = QtWidgets.QGraphicsPixmapItem(pixmap_resized)
        item = QtWidgets.QGraphicsPixmapItem(pixmap)
        self.scene = QtWidgets.QGraphicsScene()
        #self.scene.setSceneRect(0, 0, 680, 720)
        self.scene.addItem(item)
        self.graphicsView.setScene(self.scene)
        self.graphicsView.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)
        #self.graphicsView.setFixedSize(680, 750)
        #self.graphicsView.setAlignment(alignment=CENTER)
        
        self.facesearch.send_frame(frame)
        #self.drawFaceDetect()
        current_time = datetime.now().strftime("%H:%M:%S")
        self.lblTime.setText(current_time)

        #Time to open the camera
        # if self.isPrint == True:
        #     self.isPrint = False
        #     print(f"Time to open camera: {datetime.timestamp(datetime.now()) - datetime.timestamp(START_TIME_LOAD_FACE_LIST)} seconds.")

        # Time to return set default text for label
        if(datetime.timestamp(datetime.now()) - datetime.timestamp(self.displayTime) > 2):
            self.lblCode.setText("Unknown")
            self.lblName.setText("Unknown")
            #self.lblSmile.setText(arr[2])
            self.graphicsView_Bottom.setStyleSheet("background-color:#b2e5f9;border:none;")
            self.lblMessage.setText("")

    def rsFaceRecognition(self, strTest):
        arr = strTest.split(' - ')
        #print(f"{arr[0]} {arr[1]} {arr[2]}")
        self.lblCode.setText(arr[0])
        self.lblName.setText(arr[1])
        #self.lblSmile.setText(arr[2])
        self.graphicsView_Bottom.setStyleSheet("background-color:#2cc901;border:none;")
        self.lblMessage.setText("Have a nice day !!!")
        self.displayTime = datetime.now()

    def drawFaceDetect(self):
        #print(f"{self.face_pos.left}")
        if self.face_pos.left > 0 and self.face_pos.top > 0 and self.face_pos.width > 0 and self.face_pos.height > 0:
            pen = QtGui.QPen(QtCore.Qt.green)
            pen.setStyle(Qt.DashLine)
            pen.setWidth(3)
            # r = QtCore.QRectF(QtCore.QPointF(self.face_pos.left, self.face_pos.top), QtCore.QSizeF(self.face_pos.width, self.face_pos.height))
            # r = QtCore.QRectF(self.face_pos.left, self.face_pos.top, self.face_pos.width, self.face_pos.height)
            # self.scene.addRect(r, pen)
            per = 8
            maxright = 636
            maxbottom = 477
            r = QtCore.QLineF(self.face_pos.left, self.face_pos.top, min(self.face_pos.left + (self.face_pos.width/per), maxright), self.face_pos.top)
            r1 = QtCore.QLineF(self.face_pos.left, self.face_pos.top, self.face_pos.left, min(self.face_pos.top + (self.face_pos.height/per), maxbottom))
            r2 = QtCore.QLineF(self.face_pos.left, min(self.face_pos.top + self.face_pos.height, maxbottom), min(self.face_pos.left + (self.face_pos.width/per), maxright), min(self.face_pos.top + self.face_pos.height, maxbottom))
            r3 = QtCore.QLineF(self.face_pos.left, min(self.face_pos.top + self.face_pos.height, maxbottom), self.face_pos.left, min((self.face_pos.top + self.face_pos.height) - (self.face_pos.height/per), maxbottom))
            r4 = QtCore.QLineF(min(self.face_pos.left + self.face_pos.width, maxright), self.face_pos.top, min((self.face_pos.left + self.face_pos.width) - (self.face_pos.width/per), maxright), self.face_pos.top)
            r5 = QtCore.QLineF(min(self.face_pos.left + self.face_pos.width, maxright), self.face_pos.top, min(self.face_pos.left + self.face_pos.width, maxright), min(self.face_pos.top + (self.face_pos.height/per), maxbottom))
            r6 = QtCore.QLineF(min(self.face_pos.left + self.face_pos.width, maxright), min(self.face_pos.top + self.face_pos.height, maxbottom), min(self.face_pos.left + self.face_pos.width, maxright), min((self.face_pos.top + self.face_pos.height) - (self.face_pos.height/per), maxbottom))
            r7 = QtCore.QLineF(min(self.face_pos.left + self.face_pos.width, maxright), min(self.face_pos.top + self.face_pos.height, maxbottom), min((self.face_pos.left + self.face_pos.width) - (self.face_pos.width/per), maxright), min(self.face_pos.top + self.face_pos.height, maxbottom))
            self.scene.addLine(r, pen)
            self.scene.addLine(r1, pen)
            self.scene.addLine(r2, pen)
            self.scene.addLine(r3, pen)
            self.scene.addLine(r4, pen)
            self.scene.addLine(r5, pen)
            self.scene.addLine(r6, pen)
            self.scene.addLine(r7, pen)
            self.scene.setStickyFocus(True)
    
    def closeApp(self):
        print("Pressed Close Button")
        self.need_to_exit = True
        self.capture.running = False
        self.facesearch.running = False
        Recognize.close()

    def reloadFaceList(self):
        self.facepro = FaceProccess()
        FACE_LIST = self.facepro.Load_Face_List()
        print(f"Reload:{len(FACE_LIST)}")

    def updateVersion(self):
        #Recognize.close()
        #app.quit()
        #os.system("python3 ./main.py")
        #app.exit()
        #time.sleep(10)
        os.system("cp ~/Desktop/overtime.png ./Spartronics-Stacked-TM-FullColor.png")
        os.system("reboot")
        print("Restarting...")

    def retranslateUi(self, Recognize):
        _translate = QtCore.QCoreApplication.translate
        Recognize.setWindowTitle(_translate("Recognize", "Face Recognition Appication"))
        #self.lblWelcome.setText(_translate("Recognize", "WELCOME TO SPATRONICS VIETNAM"))
        self.lblTime.setText(_translate("Recognize", "00:00:00"))
        self.lblMessage.setText(_translate("Recognize", ""))
        self.label_4.setText(_translate("Recognize", "Code:"))
        self.lblCode.setText(_translate("Recognize", "Unknown"))
        self.label_6.setText(_translate("Recognize", "Name:"))
        self.lblName.setText(_translate("Recognize", "Unknown"))
        self.lblDate.setText(_translate("Recognize", datetime.now().strftime("%A, %d %b, %Y")))

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    Recognize = QtWidgets.QMainWindow()
    ui = Ui_Recognize()
    ui.setupUi(Recognize)
    #Recognize.showFullScreen()
    Recognize.show() 
    sys.exit(app.exec_())
