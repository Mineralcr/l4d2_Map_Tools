# l4d2_Map_Tools
Simple map tool, including automatic detection and suppression of dictionaries, and automatic removal of unuseful files on the map for server to reduce file size

简易的地图处理工具，包括自动检测、压制字典，自动删除地图中服务器不需要的文件以降低体积.
# Attention
My Python version is 3.12

After installing the library "vpk", enter the source code, find the newVPK class, and modify the vpk version to 1. (The vpk version of L4D2 is 1, while the default version of this library is 2, which is the version of csgo, etc.)

我的Python版本为3.12

在安装了三方库"vpk"之后，进入库源码，找到"newVPK"类，将vpk版本修改为1.(求生之路vpk版本为1，而这个三方库默认版本为2，这是csgo等游戏的默认版本)
# Usage

Only one map can be processed at a time, so when importing a VPK file, please ensure that the entire VPK file is a map; When importing a compressed file, please ensure that there is only one map in the whole compressed file; The compressed file can be composed of multiple vpks, which can be different parts of the map So when the map is composed of multiple vpks, please compress it into a compressed file first

一次只能处理一张地图，所以当输入vpk文件时，请保证整个vpk文件就是一张地图；当输入压缩文件时，请保证整个压缩文件里只有一张地图；压缩文件可以由多个VPK构成，这些VPK可以分别是这张地图的不同部分.所以当地图由多个vpk构成，请先压缩为压缩文件.

