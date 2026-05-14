#pragma once
#ifdef USBAPI_EXPORTS
#define USB_API __declspec(dllexport) 
#else
#define USB_API __declspec(dllimport) 
#endif
#ifdef __cplusplus
extern "C" {
#endif // __cplusplus

	USB_API	int InitLibusb();

	USB_API void DinitLibusb();

	USB_API int Connect(int vid, int pid);

	USB_API int DisConnect();

	USB_API int Write(const char *send_buffer, unsigned int len);

	USB_API int Read(unsigned char *recv_buffer, int size);


#ifdef __cplusplus
}
#endif //