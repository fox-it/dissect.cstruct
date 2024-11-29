struct sockaddr_in {

  /* Pad to size of `struct sockaddr'.  */
  // unsigned char sin_zero[sizeof(struct sockaddr) - __SOCKADDR_COMMON_SIZE -
  //                        sizeof(in_port_t) - sizeof(struct in_addr)];
  unsigned char sin_zero[ 10
    -2];

};


 



 



 

