import SocketServer
import re
import string
import socket
import threading

rx_register = re.compile("^REGISTER")
rx_invite = re.compile("^INVITE")
rx_ack = re.compile("^ACK")
rx_cancel = re.compile("^CANCEL")
#rx_cancel_cseq = re.compile("CANCEL")
#rx_bye = re.compile("^BYE")
#rx_bye_cseq = re.compile("BYE")
rx_from = re.compile("^From:")
rx_to = re.compile("^To:")
rx_tag = re.compile(";tag")
rx_contact = re.compile("^Contact:")
rx_uri = re.compile("sip:([^@]*)@([^;>$]*)")
rx_addr = re.compile("sip:([^ ;>$]*)")
rx_addrport = re.compile("([^:]*):(.*)")
rx_code = re.compile("^SIP/2.0 ([^ ]*)")
rx_invalid = re.compile("^192\.168")
rx_invalid2 = re.compile("^10\.")
#rx_cseq = re.compile("^CSeq:")
rx_callid = re.compile("Call-ID: (.*)$")
#rx_rr = re.compile("^Record-Route:")
# Linphone bug
rx_rr = re.compile("^Record-.oute:")
rx_request_uri = re.compile("^([^ ]*) sip:([^ ]*) SIP/2.0")

# global dictionnary
registrar = {}
context = {}

class RecvClient(threading.Thread):
    def __init__(self, csock, ssock,client_address):
        threading.Thread.__init__(self)
        self.csock = csock
        self.ssock = ssock
        self.client_address = client_address
    def run(self):
        callid = ""
        received = self.csock.recv(4096)
        while received:
            print "---\n>> client received:\n%s\n---" % received
            disconnect = False
            code = ""
            #contact = False
            data = []
            for line in received.split("\r\n"):
                md = rx_callid.search(line)
                if md:
                    callid = md.group(1)
                md = rx_code.search(line)
                if md:
                    code = md.group(1)
                    if int(code) == 200:
                        disconnect = True
                if not rx_rr.search(line):
                    data.append(line)
            received =  string.join(data,"\r\n")
            print "---\n>> server send:\n%s\n---" % received
            self.ssock.sendto(received,self.client_address)            
            if disconnect == False:
                received = self.csock.recv(4096)
            else:
                print "disconnected client received"
                break

        if len(callid) > 0:
            if context.has_key(callid):
                del context[callid]
        self.csock.close()
        self.csock = None



class UDPHandler(SocketServer.BaseRequestHandler):   
    
    def debugRegister(self):
        print "\n--- REGISTRAR ---"
        print "-----------------"
        for key in registrar.keys():
            print "%s -> %s" % (key,registrar[key])
        print "-----------------"
        
    def uriToAddress(self,uri):
        addr = ""
        port = 0
        addrport = registrar[uri]
        md = rx_addrport.match(addrport)
        if md:
            addr = md.group(1)
            port = int(md.group(2))
        else:
            addr = addrport
            port = 5060
        return (addr,port)
        
                    
    def parseRequest(self):
        destination = ""
        origin = ""
        callid = ""
        for line in self.data:
            if rx_to.search(line):
                md = rx_uri.search(line)
                if md:
                    destination = "%s@%s" %(md.group(1),md.group(2))
            if rx_from.search(line):
                md = rx_uri.search(line)
                if md:
                    origin = "%s@%s" %(md.group(1),md.group(2))
            md = rx_callid.search(line)
            if md:
                callid = md.group(1)
        return (origin, destination, callid)
        
    def sendResponse(self,code):
        request_uri = "SIP/2.0 " + code
        self.data[0]= request_uri
        index = 0
        for line in self.data:
            if rx_to.search(line):
                if not rx_tag.search(line):
                        self.data[index] = "%s%s" % (line,";tag=123456")
            index += 1
        text = string.join(self.data,"\r\n")
        #print text
        self.socket.sendto(text,self.client_address)
        print "---\n<< server send:\n%s\n---" % text
        
    def processRegister(self):
        fromm = ""
        contact = ""
        size = len(self.data)
        for line in self.data:
            if rx_to.search(line):
               md = rx_uri.search(line)
               if md:
                    fromm = "%s@%s" % (md.group(1),md.group(2))
            if rx_contact.search(line):
               md = rx_uri.search(line)
               if md:
                    contact = md.group(2)
               else:
                    md = rx_addr.search(line)
                    if md:
                        contact = md.group(1)     
            
       
        print "From: %s - Contact: %s" % (fromm,contact)
        print "Client address: %s:%s" % self.client_address
        registrar[fromm]=contact
        
        self.debugRegister()
        
        if rx_invalid.search(contact) or rx_invalid2.search(contact):
            self.sendResponse("488 Not Acceptable Here")
        else:
            self.sendResponse("200 0K")
        
          
    def processInvite(self):
        #text = string.join(self.data,"\n")
        #print text
        rr = ""
        origin,destination,callid = self.parseRequest()
        if len(origin) > 0:
            print "origin %s" % origin
            if registrar.has_key(origin):
                addrport = registrar[origin]
                rr = "Record-Route: <sip:%s;lr>" % addrport
        if len(destination) > 0:
            print "destination %s" % destination
            if registrar.has_key(destination):
                addr,port = self.uriToAddress(destination)
                print "Send INVITE to %s:%s" %(addr,port)
                # change request uri
                md = rx_request_uri.search(self.data[0])
                if md:
                    method = md.group(1)
                    uri = md.group(2)
                    if registrar.has_key(uri):
                        uri = "sip:%s" % registrar[uri]
                        self.data[0] = "%s %s SIP/2.0" % (method,uri)
                if context.has_key(callid):
                    self.sock = context[callid][0]
                else:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    print "socket timeout = %s" % socket.getdefaulttimeout()
                    context[callid]=[self.sock,addr,port,rr]
                    t = RecvClient(self.sock,self.socket,self.client_address)
                    t.daemon = True
                    t.start()
                # insert Record-Route
                if len(rr) > 0:
                    self.data.insert(1,rr)
                text = string.join(self.data,"\r\n")
                self.sock.sendto(text , (addr, port))
                print "---\n<< client send:\n%s\n---" % text
                
            else:
                self.sendResponse("480 Temporarily Unavailable")
                
    def processAck(self):
        origin,destination,callid = self.parseRequest()
        if context.has_key(callid):
            self.sock,addr,port,rr = context[callid]
            print "Send ACK to %s:%s" %(addr,port)
            if len(rr) > 0:
                self.data.insert(1,rr)
            text = string.join(self.data,"\r\n")
            self.sock.sendto(text , (addr, port))
            print "---\n<< client send:\n%s\n---" % text
            self.sock.close()
            del context[callid]
        else:
            origin,destination,callid = self.parseRequest()
            if len(destination) > 0:
                print "destination %s" % destination
                if registrar.has_key(destination):
                    addr,port = self.uriToAddress(destination)
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    print "socket timeout = %s" % socket.getdefaulttimeout()
                    text = string.join(self.data,"\r\n")
                    self.sock.sendto(text , (addr, port))
                    print "---\n<< client send:\n%s\n---" % text
                    self.sock.close()
           
    def processOtherRequest(self):
        origin,destination,callid = self.parseRequest()
        if context.has_key(callid):
            self.sock,addr,port,rr = context[callid]
            print "Send Other to %s:%s" %(addr,port)
            if len(rr) > 0:
                self.data.insert(1,rr)
            text = string.join(self.data,"\r\n")
            self.sock.sendto(text , (addr, port))
            print "---\n<< client send:\n%s\n---" % text   
        else:
            self.sendResponse("404 Not Found")                    
    
    def processRequest(self):
        #print "processRequest"
        if len(self.data) > 0:
            request_uri = self.data[0]
            if rx_register.search(request_uri):
                self.processRegister()
            elif rx_invite.search(request_uri):
                self.processInvite()
            elif rx_ack.search(request_uri):
                self.processAck()
            # elif rx_bye.search(request_uri):
                # self.processInvite()
            elif rx_cancel.search(request_uri):
                self.processOtherRequest()
            # elif rx_code.search(request_uri):
                # print "unexpected code: %s" % request_uri
            else:
                print "request_uri %s"     % request_uri          
                #print "message %s unknown" % self.data

    """
    def setup(self):
        pass
        #print "setup"
    """
    
    def handle(self):
        #print "handle"
        #print self.server
        socket.setdefaulttimeout(32)
        self.data = self.request[0].split("\r\n")
        self.socket = self.request[1]
        print self.socket
        print "---\n>> server received:\n%s\n---" %  self.request[0]
        if len(self.data) > 1:
            print "---\n>> server received:\n%s\n---" %  self.request[0]
            self.processRequest()

    """
    def finish(self):
        pass
        #print "finish"
        #self.socket.close()
    """
if __name__ == "__main__":
    #HOST, PORT = "127.0.0.1", 5060
    HOST, PORT = '0.0.0.0', 5060
    server = SocketServer.UDPServer((HOST, PORT), UDPHandler)
    server.serve_forever()
