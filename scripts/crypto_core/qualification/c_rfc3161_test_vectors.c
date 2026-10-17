/* Disposable synthetic fixtures generated inside the protected qualification DLL.
 * Private test keys never leave this function. No clock, file, env or network
 * input; fixed test instants and nonce. Key generation uses OS entropy, so byte
 * reproducibility across generations is not claimed. Never a real TSA/root.
 */
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/pkcs7.h>
#include <openssl/ts.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

static int extension(X509 *cert,X509 *issuer,int nid,const char *text) {
    X509V3_CTX ctx; X509_EXTENSION *e; int ok;
    X509V3_set_ctx(&ctx,issuer,cert,NULL,NULL,0);
    e=X509V3_EXT_conf_nid(NULL,&ctx,nid,(char *)text);
    ok=e && X509_add_ext(cert,e,-1); X509_EXTENSION_free(e); return ok;
}

static X509 *certificate(EVP_PKEY *key,X509 *issuer,EVP_PKEY *issuer_key,int ca,int expired) {
    X509 *cert=X509_new(); X509_NAME *name;
    if(!cert || !X509_set_version(cert,2) || !ASN1_INTEGER_set(X509_get_serialNumber(cert),ca?1:2) ||
       !ASN1_TIME_set(X509_getm_notBefore(cert),(time_t)1600000000) ||
       !ASN1_TIME_set(X509_getm_notAfter(cert),(time_t)(expired?1700000000:1900000000)) ||
       !X509_set_pubkey(cert,key)) goto bad;
    name=X509_get_subject_name(cert);
    if(!X509_NAME_add_entry_by_txt(name,"CN",MBSTRING_ASC,(const unsigned char *)(ca?"SYNTHETIC QUALIFICATION ROOT":"SYNTHETIC QUALIFICATION SIGNER"),-1,-1,0) ||
       !X509_set_issuer_name(cert,issuer?X509_get_subject_name(issuer):name)) goto bad;
    if(!issuer) issuer=cert;
    if(!extension(cert,issuer,NID_basic_constraints,ca?"critical,CA:TRUE":"critical,CA:FALSE") ||
       !extension(cert,issuer,NID_key_usage,ca?"critical,keyCertSign,cRLSign":"critical,digitalSignature") ||
       !extension(cert,issuer,NID_subject_key_identifier,"hash") ||
       !extension(cert,issuer,NID_authority_key_identifier,"keyid:always") ||
       (!ca && !extension(cert,issuer,NID_ext_key_usage,"critical,timeStamping")) ||
       !X509_sign(cert,issuer_key,EVP_sha256())) goto bad;
    return cert;
bad: X509_free(cert); return NULL;
}

static X509_CRL *crl_for(X509 *root,EVP_PKEY *key,int revoked) {
    X509_CRL *crl=X509_CRL_new(); ASN1_TIME *start=NULL,*end=NULL,*when=NULL;
    X509_REVOKED *entry=NULL; ASN1_INTEGER *serial=NULL;
    if(!crl || !(start=ASN1_TIME_set(NULL,(time_t)1799999000)) ||
       !(end=ASN1_TIME_set(NULL,(time_t)1800100000)) || !X509_CRL_set_version(crl,1) ||
       !X509_CRL_set_issuer_name(crl,X509_get_subject_name(root)) ||
       !X509_CRL_set1_lastUpdate(crl,start) || !X509_CRL_set1_nextUpdate(crl,end)) goto bad;
    if(revoked) {
        entry=X509_REVOKED_new(); serial=ASN1_INTEGER_new(); when=ASN1_TIME_set(NULL,(time_t)1799999900);
        if(!entry || !serial || !when || !ASN1_INTEGER_set(serial,2) ||
           !X509_REVOKED_set_serialNumber(entry,serial) || !X509_REVOKED_set_revocationDate(entry,when) ||
           !X509_CRL_add0_revoked(crl,entry)) goto bad;
        entry=NULL;
    }
    if(!X509_CRL_sort(crl) || !X509_CRL_sign(crl,key,EVP_sha256())) goto bad;
    ASN1_TIME_free(start); ASN1_TIME_free(end); ASN1_TIME_free(when); ASN1_INTEGER_free(serial); return crl;
bad:
    X509_CRL_free(crl); X509_REVOKED_free(entry); ASN1_TIME_free(start);
    ASN1_TIME_free(end); ASN1_TIME_free(when); ASN1_INTEGER_free(serial); return NULL;
}

static int fixed_time(TS_RESP_CTX *ctx,void *data,long *sec,long *usec) {
    (void)ctx;(void)data;*sec=1800000000L;*usec=0;return 1;
}

static TS_RESP *response_for(TS_REQ *req,X509 *leaf,EVP_PKEY *key,X509 *root,int accuracy) {
    TS_RESP_CTX *ctx=TS_RESP_CTX_new(); STACK_OF(X509) *certs=sk_X509_new_null();
    TS_RESP *resp=NULL; BIO *bio=NULL; unsigned char *der=NULL; int n;
    if(!ctx || !certs || !sk_X509_push(certs,root) ||
       !TS_RESP_CTX_set_signer_cert(ctx,leaf) || !TS_RESP_CTX_set_signer_key(ctx,key) ||
       !TS_RESP_CTX_set_signer_digest(ctx,EVP_sha256()) ||
       !TS_RESP_CTX_set_ess_cert_id_digest(ctx,EVP_sha256()) ||
       !TS_RESP_CTX_set_def_policy(ctx,TS_REQ_get_policy_id(req)) ||
       !TS_RESP_CTX_set_certs(ctx,certs) || !TS_RESP_CTX_add_md(ctx,EVP_sha256()) ||
       (accuracy && !TS_RESP_CTX_set_accuracy(ctx,1,100,10))) goto done;
    TS_RESP_CTX_set_time_cb(ctx,fixed_time,NULL);
    TS_RESP_CTX_add_flags(ctx,TS_ESS_CERT_ID_CHAIN | TS_ORDERING);
    n=i2d_TS_REQ(req,&der); if(n<=0 || !(bio=BIO_new_mem_buf(der,n))) goto done;
    resp=TS_RESP_create_response(ctx,bio);
    if(resp && !TS_RESP_get_tst_info(resp)) {TS_RESP_free(resp);resp=NULL;}
done:
    BIO_free(bio);OPENSSL_free(der);sk_X509_free(certs);TS_RESP_CTX_free(ctx);return resp;
}

EXPORT int cqual_generate_test_vectors(unsigned char *out,size_t capacity,size_t *written) {
    EVP_PKEY *root_key=NULL,*leaf_key=NULL,*other_key=NULL;
    X509 *root=NULL,*leaf=NULL,*expired=NULL,*other_root=NULL;
    X509_CRL *good=NULL,*revoked=NULL; TS_REQ *req=NULL,*other_req=NULL;
    TS_RESP *resp=NULL,*no_accuracy=NULL,*no_ess=NULL,*other_policy=NULL,*expired_resp=NULL;
    TS_MSG_IMPRINT *mi=NULL; X509_ALGOR *alg=NULL; ASN1_OBJECT *oid=NULL;
    ASN1_INTEGER *nonce=NULL; unsigned char imprint[32]; size_t used=0; int ok=0,n,index;
    PKCS7_SIGNER_INFO *si; unsigned char *p;
    if(written) *written=0;
    if(!out || !written || capacity>16*1024*1024 || capacity<65536 ||
       !OPENSSL_init_crypto(OPENSSL_INIT_NO_LOAD_CONFIG | OPENSSL_INIT_NO_ATEXIT,NULL)) return 0;
    memset(imprint,'i',sizeof(imprint));
    root_key=EVP_PKEY_Q_keygen(NULL,NULL,"RSA",(size_t)2048);
    leaf_key=EVP_PKEY_Q_keygen(NULL,NULL,"RSA",(size_t)2048);
    other_key=EVP_PKEY_Q_keygen(NULL,NULL,"RSA",(size_t)2048);
    if(!root_key || !leaf_key || !other_key || !(root=certificate(root_key,NULL,root_key,1,0)) ||
       !(leaf=certificate(leaf_key,root,root_key,0,0)) ||
       !(expired=certificate(leaf_key,root,root_key,0,1)) ||
       !(other_root=certificate(other_key,NULL,other_key,1,0)) ||
       !(good=crl_for(root,root_key,0)) || !(revoked=crl_for(root,root_key,1))) goto done;
    req=TS_REQ_new();mi=TS_MSG_IMPRINT_new();alg=X509_ALGOR_new();nonce=ASN1_INTEGER_new();oid=OBJ_txt2obj("1.2.3.4.5",1);
    if(!req || !mi || !alg || !nonce || !oid || !ASN1_INTEGER_set_uint64(nonce,UINT64_C(0x123456789abcdef))) goto done;
    X509_ALGOR_set0(alg,OBJ_nid2obj(NID_sha256),V_ASN1_NULL,NULL);
    if(!TS_MSG_IMPRINT_set_algo(mi,alg) || !TS_MSG_IMPRINT_set_msg(mi,imprint,32) ||
       !TS_REQ_set_version(req,1) || !TS_REQ_set_msg_imprint(req,mi) || !TS_REQ_set_policy_id(req,oid) ||
       !TS_REQ_set_nonce(req,nonce) || !TS_REQ_set_cert_req(req,1) ||
       !(resp=response_for(req,leaf,leaf_key,root,1)) || !(no_accuracy=response_for(req,leaf,leaf_key,root,0)) ||
       !(expired_resp=response_for(req,expired,leaf_key,root,1))) goto done;
    no_ess=ASN1_item_dup(ASN1_ITEM_rptr(TS_RESP),resp);
    if(!no_ess) goto done;
    si=sk_PKCS7_SIGNER_INFO_value(PKCS7_get_signer_info(TS_RESP_get_token(no_ess)),0);
    index=X509at_get_attr_by_NID(si->auth_attr,NID_id_smime_aa_signingCertificateV2,-1);
    if(index<0) goto done;
    X509_ATTRIBUTE_free(X509at_delete_attr(si->auth_attr,index));
    if(!PKCS7_SIGNER_INFO_set(si,leaf,leaf_key,EVP_sha256()) || !PKCS7_SIGNER_INFO_sign(si)) goto done;
    other_req=ASN1_item_dup(ASN1_ITEM_rptr(TS_REQ),req); ASN1_OBJECT_free(oid);oid=OBJ_txt2obj("1.2.3.4.6",1);
    if(!other_req || !oid || !TS_REQ_set_policy_id(other_req,oid) || !(other_policy=response_for(other_req,leaf,leaf_key,root,1))) goto done;
#define PACK(F,OBJ) do { n=F(OBJ,NULL); if(n<=0 || (size_t)n>capacity-used || capacity-used-(size_t)n<4) goto done; \
    out[used]=(unsigned char)((unsigned)n>>24);out[used+1]=(unsigned char)((unsigned)n>>16);out[used+2]=(unsigned char)((unsigned)n>>8);out[used+3]=(unsigned char)n; \
    p=out+used+4;if(F(OBJ,&p)!=n) goto done;used+=4+(size_t)n; } while(0)
    PACK(i2d_TS_REQ,req);PACK(i2d_TS_RESP,resp);PACK(i2d_X509,root);
    PACK(i2d_X509_CRL,good);PACK(i2d_X509_CRL,revoked);PACK(i2d_TS_RESP,no_accuracy);
    PACK(i2d_X509,leaf);PACK(i2d_TS_RESP,no_ess);PACK(i2d_TS_RESP,other_policy);
    PACK(i2d_TS_RESP,expired_resp);PACK(i2d_X509,other_root);
#undef PACK
    *written=used;ok=1;
done:
    EVP_PKEY_free(root_key);EVP_PKEY_free(leaf_key);EVP_PKEY_free(other_key);
    X509_free(root);X509_free(leaf);X509_free(expired);X509_free(other_root);
    X509_CRL_free(good);X509_CRL_free(revoked);TS_REQ_free(req);TS_REQ_free(other_req);
    TS_RESP_free(resp);TS_RESP_free(no_accuracy);TS_RESP_free(no_ess);TS_RESP_free(other_policy);TS_RESP_free(expired_resp);
    TS_MSG_IMPRINT_free(mi);X509_ALGOR_free(alg);ASN1_OBJECT_free(oid);ASN1_INTEGER_free(nonce);
    if(!ok) {OPENSSL_cleanse(out,capacity);*written=0;}return ok;
}
