import _thread
import datetime
import pickle
import socket
import time
from socket import *
import select
import threading
import sqlite3
import os
import ssl

"""
Server by Alon Levy
"""

file = __file__


class Server:
    def __init__(self):
        """Base creation of all essential variables and use of functions"""
        if not os.path.exists('Images/'):
            os.makedirs('Images/')
        if not os.path.exists('Attractions_images/'):
            os.makedirs('Attractions_images/')
        self.server = socket(AF_INET, SOCK_STREAM)
        self.server = ssl.wrap_socket(self.server, server_side=True, keyfile='privkey.pem', certfile='certificate.pem')
        self.server.bind(('127.0.0.1', 50000))
        self.server.listen(5)
        self.servertime = datetime.datetime.today().date()
        self.readables = [self.server]
        self.writeables = [self.server]
        self.admin_dict = {}
        self.BUF = 2048
        self.PORT = 50000
        self.rooms = []
        self.occ = []
        self.conn = sqlite3.connect('Databases/registered.db')
        self.conn.cursor().execute('CREATE TABLE IF NOT EXISTS Registered(Fullname TEXT, Email TEXT,'
                                   ' Country TEXT, Password TEXT, Admin BIT);')
        self.conn.cursor().execute('CREATE TABLE IF NOT EXISTS Bought(RoomName TEXT, '
                                   'Buyer TEXT, First TEXT, Last TEXT, RATING INT, TOTAL INT);')
        self.conn.close()
        self.conn = sqlite3.connect('Databases/database.db')
        self.conn.cursor().execute('CREATE TABLE IF NOT EXISTS Offered(RoomName TEXT,By TEXT, Coordinates TEXT,'
                                   ' Price INT, First TEXT, Last TEXT, ImagePath TEXT, RATING INT, Conditions TEXT);')
        self.conn.cursor().execute(
            'CREATE TABLE IF NOT EXISTS Attractions(Name TEXT,Coordinates TEXT, ImagePath TEXT, Radius INT);')
        self.conn.close()
        self.lst = os.listdir('Images/')
        self.att_lst = os.listdir('Attractions_images/')
        threading.Thread(target=self.listen).start()
        print('LISTENING ON 50000')

    def send_database(self, sock, name):
        """send database by its name to a user"""
        filename = f'Databases/{name}.db'
        with open(filename, 'rb') as txt:
            length = os.path.getsize(filename)
            send = pickle.dumps(length)
            sock.send(send)
            s = 0
            while s != length:
                data = txt.read(self.BUF)
                s += len(data)
                sock.send(data)
        sock.send('DATE'.encode())
        sock.send(pickle.dumps(self.servertime))

    def getfile(self, sock, name):
        """get image from user"""
        data = sock.recv(self.BUF)
        img = pickle.loads(data)
        s = 0
        with open(f'Images/{name}', 'wb') as txt:
            while s != img:
                data2 = sock.recv(self.BUF)
                txt.write(data2)
                s += len(data2)

    def get_attraction_file(self, sock, name):
        """get attraction image from admin"""
        data = sock.recv(self.BUF)
        img = pickle.loads(data)
        s = 0
        with open(f'Attractions_images/{name}', 'wb') as txt:
            while s != img:
                data2 = sock.recv(self.BUF)
                txt.write(data2)
                s += len(data2)

    def timer(self, row):
        """timer starts in case of room being watched by user (60 seconds unless was closed beforehand)"""
        time.sleep(60)
        if row in self.occ:
            self.occ.remove(row)

    def listen(self):
        """listens to all, most of the client interactions are made here"""
        while 1:
            read, write, ex = select.select(self.readables, self.writeables, [])
            for sock in read:
                if sock == self.server:
                    client, addr = self.server.accept()
                    print(f'{addr} Connected')
                    client.send(pickle.dumps(self.lst))
                    client.send(pickle.dumps(self.att_lst))
                    self.readables.append(client)
                    self.writeables.append(client)
                    _thread.start_new_thread(self.sendimages, (client,))
                else:
                    try:
                        data = sock.recv(self.BUF)
                    except ConnectionResetError:
                        print(f'{sock.getpeername()} Disconnected')
                        self.readables.remove(sock)
                        self.writeables.remove(sock)
                        if sock in self.admin_dict.values():
                            remove = None
                            for key, value in self.admin_dict.items():
                                if sock == value:
                                    remove = key
                                    break
                            del self.admin_dict[remove]
                        break
                    if not data:
                        print(f'{sock.getpeername()} Disconnected')
                        self.readables.remove(sock)
                        self.writeables.remove(sock)
                        if sock in self.admin_dict.values():
                            remove = None
                            for key, value in self.admin_dict.items():
                                if sock == value:
                                    remove = key
                                    break
                            del self.admin_dict[remove]
                        break
                    try:
                        datacontent = data.decode()
                        print(datacontent)
                    except:
                        datacontent = ""
                    if 'ADD' in datacontent:
                        values = datacontent[4:].split('. ')
                        self.getfile(sock, values[6])
                        self.addroom(values, sock)
                    elif 'ATTRACTION' in datacontent:
                        values = datacontent[11:].split('. ')
                        self.get_attraction_file(sock, values[1])
                        self.add_attraction(values)
                        _thread.start_new_thread(self.broadcast_files, ())
                    elif datacontent == 'CRED':
                        data = sock.recv(self.BUF)
                        data = pickle.loads(data)
                        if type(data) == list and len(data) == 4:  # register detected
                            self.registeruser(data, sock)
                        elif type(data) == list and len(data) == 2:  # login detected
                            user, ret, specific_order, all_orders = self.loginuser(data, sock, True)
                            if ret is not None:
                                sock.send(pickle.dumps([ret, user, all_orders]))
                                if user[4] == 1:  # is Admin
                                    sock.send('PUSH'.encode())
                                    self.send_database(sock, 'registered')
                                _thread.start_new_thread(self.user_rate, (ret, sock, specific_order))
                    elif datacontent == 'BUY':
                        data = pickle.loads(sock.recv(self.BUF))
                        self.conn2 = sqlite3.connect('Databases/registered.db')
                        self.conn2.cursor().execute('INSERT INTO Bought(RoomName, Buyer, First, Last, TOTAL)  '
                                                    'VALUES(?,?,?,?,?)',
                                                    (data[0], data[-1], data[4], data[5], data[3]))
                        self.conn2.commit()
                        self.conn2.close()
                        _thread.start_new_thread(self.inform_admins,
                                                 ())  # inform all admins on room purchase (db content)
                    elif datacontent == 'OCC':
                        data = sock.recv(self.BUF)
                        data = pickle.loads(data)
                        if data not in self.occ:
                            self.occ.append(data)
                            _thread.start_new_thread(self.timer, (data,))
                        else:
                            sock.send('DESTROY'.encode())
                    elif datacontent == 'REM':
                        data = sock.recv(self.BUF)
                        data = pickle.loads(data)
                        if data in self.occ:
                            self.occ.remove(data)
                    elif datacontent == 'UPDATE':
                        data = sock.recv(self.BUF)
                        data = pickle.loads(data)
                        self.conn = sqlite3.connect('Databases/registered.db')
                        self.conn.cursor().execute(f'DELETE FROM Bought WHERE RoomName=? AND Buyer=?;',
                                                   (data[0], data[-1]))
                        self.conn.commit()
                        self.conn.close()
                        _thread.start_new_thread(self.inform_admins, ())
                    elif datacontent == 'DATE':
                        data = pickle.loads(sock.recv(self.BUF))
                        self.servertime = data
                        _thread.start_new_thread(self.broadcast_new_date, (data,))
                    elif datacontent == 'RATE':
                        data = pickle.loads(sock.recv(self.BUF))
                        user, ret, specific_order, all_orders = self.loginuser(data, sock, False)
                        _thread.start_new_thread(self.user_rate, (ret, sock, specific_order))
                    elif datacontent == 'RATING':
                        rating = pickle.loads(sock.recv(self.BUF))
                        self.conn = sqlite3.connect('Databases/registered.db')
                        self.conn.cursor().execute(
                            f'UPDATE Bought SET RATING={rating[0]} WHERE RoomName="{rating[1]}" AND Buyer="{rating[2]}"')  # Rating | Roomname | Buyer
                        self.conn.commit()
                        self.conn.close()
                        self.update_total_rating(rating[1])
                        _thread.start_new_thread(self.broadcast_files, ())
                    elif datacontent == 'CHECK':
                        data = pickle.loads(sock.recv(self.BUF))
                        _thread.start_new_thread(self.check_dates, (data[0], data[1], data[2], sock))
                    elif 'MAKE' in datacontent:
                        user = datacontent[5:]
                        self.make_admin(user)

    def make_admin(self, user):
        """make user an admin by an admin command"""
        conn = sqlite3.connect('Databases/registered.db')
        conn.execute(f'UPDATE Registered SET Admin=1 WHERE Email="{user}"')
        conn.commit()
        conn.close()
        _thread.start_new_thread(self.admins_broadcast, ())

    def add_attraction(self, values):
        """add an attraction with information given by admin"""
        conn = sqlite3.connect('Databases/database.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO Attractions (Name, Coordinates, ImagePath, Radius) VALUES (?,?,?,?)',
            (values[2], values[0], values[1], int(values[3])))
        conn.commit()
        conn.close()

    def admins_broadcast(self):
        """broadcast all admins updating on database change"""
        for admin in self.admin_dict.values():
            admin.send('PUSH'.encode())
            self.send_database(admin, 'registered')

    def inform_admins(self):
        """update admins on data change (not sending database itself, data only)"""
        conn = sqlite3.connect('Databases/registered.db')
        cursor = conn.cursor().execute('SELECT * FROM Bought')
        all_orders = cursor.fetchall()
        _all = []
        conn.close()
        conn = sqlite3.connect('Databases/database.db')
        for i in all_orders:
            cursor = conn.cursor().execute(f'SELECT * FROM Offered WHERE RoomName="{i[0]}"')
            rec = cursor.fetchone()
            if rec is not None:
                rec = list(rec)
                rec[4], rec[5] = i[2], i[3]  # dates purchased by user
                rec[3] = i[5]  # update price to total
                rec.append(i[1])
                _all.append(rec)
        conn.close()
        for admin in self.admin_dict.values():
            admin.send('UPDATE'.encode())
            admin.send(pickle.dumps(_all))

    def check_dates(self, row, start, finish, sock):
        """check if dates are available for purchase, sent by user to check room availability"""
        total = -row[3]  # start at deficit
        conn = sqlite3.connect('Databases/registered.db')
        cursor = conn.cursor().execute('SELECT First, Last FROM Bought WHERE RoomName=?', (row[0],))
        dates = cursor.fetchall()
        final_dates1 = []
        final_dates2 = []
        flag = True
        for date in dates:
            s = datetime.datetime.strptime(date[0], '%d/%m/%Y')
            f = datetime.datetime.strptime(date[1], '%d/%m/%Y')
            while s <= f:
                final_dates1.append(s.date())
                s += datetime.timedelta(days=1)
        while start <= finish:
            total += row[3]
            final_dates2.append(start)
            start += datetime.timedelta(days=1)
        for i in final_dates2:
            if i in final_dates1:
                flag = False
                break
        sock.send(pickle.dumps((flag, total)))

    def broadcast_files(self):
        """broadcasts images, database to all clients"""
        self.lst = os.listdir('Images/')
        self.att_lst = os.listdir('Attractions_images/')
        for sock in self.writeables:
            if sock != self.server:
                sock.send('FILES'.encode())
                sock.send(pickle.dumps(os.listdir('Images/')))
                sock.send(pickle.dumps(os.listdir('Attractions_images/')))

                for name in self.lst:
                    with open(f'Images/{name}', 'rb') as txt:
                        length = os.path.getsize(f'Images/{name}')
                        send = pickle.dumps(length)
                        s = 0
                        sock.send(send)
                        while s != length:
                            data = txt.read(self.BUF)
                            sock.send(data)
                            s += len(data)
                for name in self.att_lst:
                    with open(f'Attractions_images/{name}', 'rb') as txt:
                        length = os.path.getsize(f'Attractions_images/{name}')
                        send = pickle.dumps(length)
                        s = 0
                        sock.send(send)
                        while s != length:
                            data = txt.read(self.BUF)
                            sock.send(data)
                            s += len(data)
                self.send_database(sock, 'database')

    def user_rate(self, rec, sock, specific_order):
        """for each connected user, RATE will be sent, awaiting answer RATING from client"""
        if rec is not None:  # User bought a room
            for order in range(len(rec)):
                dur = datetime.datetime.strptime(rec[order][5], '%d/%m/%Y')
                if self.servertime > dur.date() and specific_order[order][4] is None:
                    sock.send('RATE'.encode())
                    sock.send(pickle.dumps(rec[order]))

    def update_total_rating(self, name):
        """Update total rating of a room in the Offered table based on purchases"""

        self.conn = sqlite3.connect('Databases/registered.db')
        all_rates = self.conn.cursor().execute('SELECT RATING FROM Bought WHERE RoomName=? AND RATING IS NOT NULL;',
                                               (name,)).fetchall()
        self.conn.close()
        self.conn = sqlite3.connect('Databases/database.db')
        subtotal = 0  # all ratings combined
        total = 0  # amount of ratings (only if not default - 0)
        for rate in all_rates:
            if rate != 0:
                total += 1
                subtotal += rate[0]
        if subtotal != 0:
            self.conn.cursor().execute(f'UPDATE Offered SET RATING=? WHERE RoomName=?', (subtotal / total, name))
            self.conn.commit()
            self.conn.close()

    def loginuser(self, cred, sock, flag):
        print(cred)
        """ Checks validity of credentials sent by client """
        all_orders = None
        self.conn = sqlite3.connect('Databases/registered.db')
        cursor = self.conn.cursor().execute('SELECT * FROM Registered WHERE Email=? AND Password=?',
                                            (cred[0], cred[1]))
        self.conn.commit()
        data = cursor.fetchone()
        if data is None or len(data) == 0:
            sock.send('Error: Not Found'.encode())
            return None, None, None, None
        if flag:
            sock.send(f'Success {cred[0]} {data[0]}'.encode())
        cursor = self.conn.cursor().execute(f'SELECT * FROM Bought WHERE Buyer="{cred[0]}"')
        _all = cursor.fetchall()
        self.conn.close()
        self.conn = sqlite3.connect('Databases/database.db')
        ret = []
        ret_all = []
        for i in _all:
            cursor = self.conn.cursor().execute(f'SELECT * FROM Offered WHERE RoomName="{i[0]}"')
            rec = cursor.fetchone()
            if rec is not None:
                rec = list(rec)
                rec[4], rec[5] = i[2], i[3]  # dates purchased by user
                rec[3] = i[5]  # update price to total
                ret.append(rec)
        self.conn.close()
        if data[4] == 1:  # is admin
            self.conn = sqlite3.connect('Databases/registered.db')
            self.admin_dict[data[1]] = sock
            cursor = self.conn.cursor().execute(f'SELECT * FROM Bought')
            all_orders = cursor.fetchall()
            self.conn.close()
            self.conn = sqlite3.connect('Databases/database.db')
            for i in all_orders:
                cursor = self.conn.cursor().execute(f'SELECT * FROM Offered WHERE RoomName="{i[0]}"')
                rec = cursor.fetchone()
                if rec is not None:
                    rec = list(rec)
                    rec[4], rec[5] = i[2], i[3]  # dates purchased by user
                    rec[3] = i[5]  # update price to total
                    rec.append(i[1])
                    ret_all.append(rec)
        self.conn.close()
        return data, ret, _all, ret_all

    def broadcast_new_date(self, date):
        """Broadcasts new dates to all connected users on date update"""
        for sock in self.writeables:
            if sock != self.server:
                sock.send('DATE'.encode())
                sock.send(pickle.dumps(date))

    def registeruser(self, cred, sock):
        """adds new user to registered db according to client sent information (Called upon CRED)"""
        self.conn = sqlite3.connect('Databases/registered.db')
        cursor = self.conn.cursor()
        cursor2 = self.conn.cursor().execute(f'SELECT * FROM Registered WHERE Email=?', (cred[2],))
        self.conn.commit()
        data = cursor2.fetchall()
        if len(data) != 0:
            sock.send('Error: User Found'.encode())
            return
        sock.send(f'Success {cred[1], cred[0]}'.encode())
        cursor.execute(
            'INSERT INTO Registered (Fullname, Email, Country, Password, Admin) VALUES (?,?,?,?,0)',
            (cred[0], cred[1], cred[2], cred[3]))
        self.conn.commit()
        self.conn.close()

    def addroom(self, values, sock):
        """ Checks if room exists and adds a room accordingly """
        conn = sqlite3.connect('Databases/database.db')
        try:
            cursor = conn.cursor().execute(f'SELECT * FROM Offered WHERE RoomName={values[0]}').fetchone()
            if cursor is not None:
                sock.send('Exists: Room Name is taken'.encode())
            else:
                raise ValueError
        except:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO Offered (RoomName, By, Coordinates,'
                ' Price, First, Last, ImagePath, Conditions) VALUES (?,?,?,?,?,?,?,?)',
                (values[0], values[5], values[1], values[2], values[3], values[4], values[6], values[7]))
            conn.commit()
            sock.send('Success: Added room'.encode())

        conn.close()
        _thread.start_new_thread(self.broadcast_files, ())

    def sendimages(self, sock):
        """Sends all images to a client"""
        for name in self.lst:
            with open(f'Images/{name}', 'rb') as txt:
                length = os.path.getsize(f'Images/{name}')
                send = pickle.dumps(length)
                s = 0
                sock.send(send)
                while s != length:
                    data = txt.read(self.BUF)
                    s += len(data)
                    sock.send(data)
        for name in self.att_lst:
            with open(f'Attractions_images/{name}', 'rb') as txt:
                length = os.path.getsize(f'Attractions_images/{name}')
                send = pickle.dumps(length)
                s = 0
                sock.send(send)
                while s != length:
                    data = txt.read(self.BUF)
                    sock.send(data)
                    s += len(data)
        _thread.start_new_thread(self.send_database, (sock, 'database'))


if __name__ == '__main__':
    print('___INITIALIZING___')
    s = Server()
