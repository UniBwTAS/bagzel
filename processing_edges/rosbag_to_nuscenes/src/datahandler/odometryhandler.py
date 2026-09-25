from scipy.spatial.transform import Rotation


class OdomHandler:
    def __init__(self):
        self.__x = None
        self.__y = None
        self.__z = None
        self.__yaw = None
        self.__roll = None
        self.__pitch = None
        self.__stamp = None
        self.__vx = None
        self.__vy = None
        self.__vz = None
        self.__vyaw = None
        self.__vroll = None
        self.__vpitch = None




    def setOdom(self, msg, timestamp):
        self.__stamp = timestamp# msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9 ## sec + nanosec
        self.__x = msg.pose.pose.position.x
        self.__y = msg.pose.pose.position.y
        self.__z = msg.pose.pose.position.z
        self.__qx = msg.pose.pose.orientation.x
        self.__qy = msg.pose.pose.orientation.y
        self.__qz = msg.pose.pose.orientation.z
        self.__qw = msg.pose.pose.orientation.w
        self.__vx = msg.twist.twist.linear.x
        self.__vy = msg.twist.twist.linear.y
        self.__vz = msg.twist.twist.linear.z
        self.__vroll = msg.twist.twist.angular.x
        self.__vpitch = msg.twist.twist.angular.y
        self.__vyaw = msg.twist.twist.angular.z

        rot = Rotation.from_quat([ self.__qx, self.__qy, self.__qz, self.__qw ])


        euler = rot.as_euler('xyz', degrees=True).tolist()

        self.__roll = euler[0]
        self.__pitch = euler[1]
        self.__yaw = euler[2]


    #returns [timestamp, [x,y,yaw]]
    def getOdom2D(self):
        return [self.__stamp, [self.__x, self.__y, self.__yaw]]

    #returns [timestamp, [x,y,z, roll, pitch yaw yaw]]
    def getOdom3D(self):
        return [self.__stamp, [self.__x, self.__y, self.__z, self.__roll, self.__pitch, self.__yaw]]

    def getOdomPosition(self):
        return [self.__x, self.__y, self.__z]
    def getOdomQuaternion(self):
        return [self.__qw, self.__qx, self.__qy, self.__qz]
    def getOdomEuler(self):
        return [self.__roll, self.__pitch, self.__yaw]
    def getOdomStamp(self):
        return self.__stamp
    def getOdomTwistLinear(self):
        return [self.__vx, self.__vy, self.__vz]
    def getOdomTwistAngular(self):
        return [self.__vroll, self.__vpitch, self.__vyaw]

