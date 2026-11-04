#pragma once
#include <Arduino.h>
#include <esp_http_server.h>
#include <functional>
#include <array>
#include <cstring>
#include "HttpForm.h"
// ESP-IDF owns bounded multi-session socket parsing and idle-session eviction.
// All callbacks run on its one core-0 server task. No motor access is allowed.
class NativeHttpServer {
  struct Route {NativeHttpServer *owner=nullptr;const char *path=nullptr;httpd_method_t method=HTTP_GET;std::function<void()> call;};
  std::array<Route,26> routes;size_t routeCount=0;
  struct Header {String key,value;};std::array<Header,8> headers;size_t headerCount=0;
  httpd_handle_t handle=nullptr;httpd_req_t *request=nullptr;
  HttpForm form;std::function<void()> missing;bool sent=false,overflow=false;
  esp_err_t responseResult=ESP_OK;
  uint16_t port;
  static esp_err_t dispatch(httpd_req_t *r){auto *route=static_cast<Route*>(r->user_ctx);return route->owner->serve(r,route);}
  static esp_err_t notFound(httpd_req_t *r,httpd_err_code_t){return static_cast<NativeHttpServer*>(httpd_get_global_user_ctx(r->handle))->serve(r,nullptr);}
  esp_err_t serve(httpd_req_t *r,Route *route) {
    request=r;sent=false;responseResult=ESP_OK;headerCount=0;form.count=0;
    if(r->content_len>HttpForm::MAX_BODY_BYTES){send(413,"text/plain","Body too large");request=nullptr;return ESP_FAIL;}
    if(r->content_len) {
      if(r->method!=HTTP_POST){send(400,"text/plain","Unexpected body");request=nullptr;return ESP_FAIL;}
      std::string body;body.resize(r->content_len);size_t used=0;
      const uint32_t began=millis();
      while(used<body.size()) {
        const int got=httpd_req_recv(r,&body[used],body.size()-used);
        if(got<=0||uint32_t(millis()-began)>1000){send(408,"text/plain","Request timeout");request=nullptr;return ESP_FAIL;}
        used+=size_t(got);
      }
      if(!form.parse(body)){send(400,"text/plain","Invalid form");request=nullptr;return ESP_FAIL;}
    }
    if(route)route->call();else if(missing)missing();
    if(!sent)send(500,"text/plain","No response");
    request=nullptr;return responseResult;
  }
  static const char *status(int n) {
    switch(n){case 200:return "200 OK";case 400:return "400 Bad Request";case 403:return "403 Forbidden";case 404:return "404 Not Found";case 408:return "408 Request Timeout";case 409:return "409 Conflict";case 413:return "413 Payload Too Large";case 503:return "503 Service Unavailable";case 504:return "504 Gateway Timeout";default:return "500 Internal Server Error";}
  }
 public:
  explicit NativeHttpServer(uint16_t p):port(p){}
  template<class F>void on(const char *path,httpd_method_t method,F f){if(routeCount<routes.size())routes[routeCount++]={this,path,method,f};else overflow=true;}
  template<class F>void onNotFound(F f){missing=f;}
  void collectHeaders(const char **,size_t){}
  bool begin() {
    if(handle)return true;
    if(overflow)return false;
    httpd_config_t cfg=HTTPD_DEFAULT_CONFIG();cfg.core_id=0;cfg.stack_size=16384;cfg.task_priority=4;cfg.server_port=port;
    cfg.max_open_sockets=4;cfg.backlog_conn=4;cfg.lru_purge_enable=true;cfg.max_uri_handlers=routes.size();
    cfg.max_req_hdr_len=2048;cfg.max_uri_len=128;cfg.max_resp_headers=headers.size();cfg.recv_wait_timeout=1;cfg.send_wait_timeout=1;
    cfg.global_user_ctx=this;cfg.global_user_ctx_free_fn=[](void*){};
    if(httpd_start(&handle,&cfg)!=ESP_OK){handle=nullptr;return false;}
    for(size_t i=0;i<routeCount;i++) {
      httpd_uri_t uri={};uri.uri=routes[i].path;uri.method=routes[i].method;uri.handler=dispatch;uri.user_ctx=&routes[i];
      if(httpd_register_uri_handler(handle,&uri)!=ESP_OK){httpd_stop(handle);handle=nullptr;return false;}
    }
    if(httpd_register_err_handler(handle,HTTPD_404_NOT_FOUND,notFound)!=ESP_OK){httpd_stop(handle);handle=nullptr;return false;}
    return true;
  }
  bool started()const{return handle!=nullptr;}
  bool hasArg(const char *name)const{for(size_t i=0;i<form.count;i++)if(form.fields[i].first==name)return true;return false;}
  String arg(const char *name)const{for(size_t i=0;i<form.count;i++)if(form.fields[i].first==name)return String(form.fields[i].second.data(),form.fields[i].second.size());return String();}
  bool hasHeader(const char *key)const{return request&&httpd_req_get_hdr_value_len(request,key)>0;}
  String header(const char *key)const {
    if(!request)return String();const size_t n=httpd_req_get_hdr_value_len(request,key);
    if(n>256)return String("HEADER_TOO_LONG");if(!n)return String();char out[257];
    return httpd_req_get_hdr_value_str(request,key,out,sizeof(out))==ESP_OK?String(out):String("HEADER_ERROR");
  }
  String hostHeader()const{return header("Host");}
  void sendHeader(const char *key,const char *value){if(headerCount<headers.size())headers[headerCount++]={key,value};}
  void sendBinary(int code,const char *type,const char *data,size_t length) {
    if(!request||sent)return;httpd_resp_set_status(request,status(code));httpd_resp_set_type(request,type);
    for(size_t i=0;i<headerCount;i++)httpd_resp_set_hdr(request,headers[i].key.c_str(),headers[i].value.c_str());
    sent=true;responseResult=httpd_resp_send(request,data,length);
  }
  void send(int code,const char *type,const String &data){sendBinary(code,type,data.c_str(),data.length());}
  void send_P(int code,const char *type,const char *data){sendBinary(code,type,data,strlen(data));}
};
