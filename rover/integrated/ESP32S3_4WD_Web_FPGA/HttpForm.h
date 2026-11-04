#pragma once
#include <array>
#include <string>
struct HttpForm {
  static constexpr size_t MAX_BODY_BYTES=4096;
  std::array<std::pair<std::string,std::string>,8> fields;
  size_t count=0;
  static int digit(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
  static bool decode(const std::string &s,std::string &out) {
    out.clear();
    for(size_t i=0;i<s.size();i++) {
      char c=s[i];
      if(c=='%'){if(i+2>=s.size())return false;int a=digit(s[++i]),b=digit(s[++i]);if(a<0||b<0)return false;c=char(a*16+b);}
      else if(c=='+')c=' ';
      out.push_back(c);
    }
    return true;
  }
  bool parse(const std::string &body) {
    count=0;if(body.size()>MAX_BODY_BYTES)return false;if(body.empty())return true;
    size_t from=0;
    for(;;) {
      if(count==fields.size())return false;
      const size_t end=body.find('&',from),stop=end==std::string::npos?body.size():end;
      const size_t equal=body.find('=',from);
      if(equal==std::string::npos||equal>=stop)return false;
      auto &f=fields[count];
      if(!decode(body.substr(from,equal-from),f.first)||!decode(body.substr(equal+1,stop-equal-1),f.second))return false;
      if(f.first.empty()||f.first.size()>24)return false;
      for(char c:f.first)if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')))return false;
      for(size_t i=0;i<count;i++)if(fields[i].first==f.first)return false;
      ++count;if(end==std::string::npos)return true;
      from=end+1;if(from==body.size())return false;
    }
  }
};
