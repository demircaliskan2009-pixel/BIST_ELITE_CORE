/* Offline qualification shim. Static OpenSSL 3.5.9, no DSO/engine/config.
 * No file, network, environment or wall-clock input. All trust is explicit.
 * A zero result is a cryptographic TEST result, never machine-time admission.
 */
#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <time.h>
#include <openssl/asn1.h>
#include <openssl/bn.h>
#include <openssl/crypto.h>
#include <openssl/err.h>
#include <openssl/objects.h>
#include <openssl/pkcs7.h>
#include <openssl/ts.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>

#if OPENSSL_VERSION_NUMBER != 0x30500090L
#error Exact OpenSSL 3.5.9 source is required
#endif
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
#define MAX_INPUT (4U * 1024U * 1024U)
#define MAX_CRLS 32
typedef char cqual_time_t_must_be_64_bits[sizeof(time_t)==8 ? 1 : -1];
typedef char cqual_pointer_must_be_64_bits[sizeof(void *)==8 ? 1 : -1];
#define REQUIRED_FLAGS (TS_VFY_SIGNATURE | TS_VFY_VERSION | TS_VFY_POLICY | TS_VFY_IMPRINT | TS_VFY_NONCE | TS_VFY_SIGNER)

/* Status inventory is stable across platforms and independent of OpenSSL errors. */
enum { Q_OK=0, Q_INPUT=1, Q_DER=2, Q_REQUEST=3, Q_TIME=4, Q_ACCURACY=5,
       Q_SIGNATURE_CHAIN_ESS_EKU=6, Q_SIGNER=7, Q_REVOCATION=8, Q_FLAGS=9 };

EXPORT uint32_t cqual_abi_version(void) { return 1; }
EXPORT uint64_t cqual_openssl_version(void) { return OpenSSL_version_num(); }
EXPORT uint32_t cqual_required_ts_flags(void) { return REQUIRED_FLAGS; }
EXPORT void cqual_cleanup(void) { OPENSSL_cleanup(); }

static int bounded(const unsigned char *p, size_t n) {
    return p != NULL && n > 0 && n <= MAX_INPUT && n <= LONG_MAX;
}

/* Strict time to integer microseconds, including signed fractional genTime.
 * ASN1_TIME_diff is relative to a literal epoch, never current time.
 */
static int time_us(const ASN1_TIME *value, int64_t *out) {
    ASN1_TIME *epoch = NULL;
    int days, secs, ok=0, fraction=0, digits=0, i;
    const unsigned char *s;
    int n;
    if (!value || !ASN1_TIME_check(value)) return 0;
    n=ASN1_STRING_length(value); s=ASN1_STRING_get0_data(value);
    if (n <= 0 || s[n-1] != 'Z') return 0;
    if (ASN1_STRING_type(value) == V_ASN1_GENERALIZEDTIME) {
        if (n < 15) return 0;
        if (n > 15) {
            if (s[14] != '.' || n < 17 || n > 22 || s[n-2] == '0') return 0;
            for (i=15; i<n-1; ++i) {
                if (s[i]<'0' || s[i]>'9') return 0;
                fraction=fraction*10+s[i]-'0'; ++digits;
            }
            while (digits++ < 6) fraction *= 10;
        }
    } else if (ASN1_STRING_type(value) != V_ASN1_UTCTIME || n != 13) return 0;
    epoch=ASN1_TIME_set(NULL, (time_t)0);
    if (epoch && ASN1_TIME_diff(&days, &secs, epoch, value)) {
        *out=((int64_t)days*86400+secs)*1000000+fraction; ok=1;
    }
    ASN1_TIME_free(epoch); return ok;
}

static int accuracy_us(TS_ACCURACY *a, int64_t limit, int64_t *out) {
    const ASN1_INTEGER *parts[3]; int64_t v, total=0; int i;
    const int64_t scale[3]={1000000,1000,1};
    if (!a || limit < 0) return 0;
    parts[0]=TS_ACCURACY_get_seconds(a);
    parts[1]=TS_ACCURACY_get_millis(a);
    parts[2]=TS_ACCURACY_get_micros(a);
    for (i=0; i<3; ++i) {
        if (!parts[i]) continue;
        if (!ASN1_INTEGER_get_int64(&v, parts[i]) || v<0 || v>INT64_MAX/1000000) return 0;
        if (i && (v<1 || v>999)) return 0;
        if (v*scale[i]>limit-total) return 0;
        total+=v*scale[i];
    }
    *out=total; return 1;
}

/* Strict full, direct issuer CRLs. Delta/indirect/scoped CRLs and OCSP are
 * unsupported and rejected; no network fetching and no ambient freshness.
 * A serial listed by applicable as-of evidence is rejected conservatively,
 * including revocations published after genTime. Every non-anchor needs a CRL.
 */
static int check_crls(STACK_OF(X509) *chain, STACK_OF(X509_CRL) *crls, int64_t asof) {
    int i,j,k,found; int64_t start,end,nb,na;
    X509 *cert,*issuer; X509_CRL *crl; X509_REVOKED *revoked;
    EVP_PKEY *key=NULL;
    for (i=0; i<sk_X509_num(chain)-1; ++i) {
        cert=sk_X509_value(chain,i); issuer=sk_X509_value(chain,i+1); found=0;
        if (!(X509_get_key_usage(issuer) & KU_CRL_SIGN)) return 0;
        for (j=0; j<sk_X509_CRL_num(crls); ++j) {
            crl=sk_X509_CRL_value(crls,j);
            if (X509_NAME_cmp(X509_CRL_get_issuer(crl), X509_get_subject_name(issuer))) continue;
            if (++found != 1) return 0; /* ambiguous same-issuer evidence */
            if (X509_CRL_get_ext_by_NID(crl,NID_delta_crl,-1)>=0 ||
                X509_CRL_get_ext_by_NID(crl,NID_issuing_distribution_point,-1)>=0 ||
                !time_us(X509_CRL_get0_lastUpdate(crl),&start) ||
                !time_us(X509_CRL_get0_nextUpdate(crl),&end) || start>asof || asof>=end || start>=end ||
                !time_us(X509_get0_notBefore(issuer),&nb) || !time_us(X509_get0_notAfter(issuer),&na) || start<nb || start>na) return 0;
            for (k=0; k<X509_CRL_get_ext_count(crl); ++k)
                if (X509_EXTENSION_get_critical(X509_CRL_get_ext(crl,k))) return 0;
            key=X509_get_pubkey(issuer);
            k=key && X509_CRL_verify(crl,key)==1;
            EVP_PKEY_free(key); key=NULL;
            if (!k || X509_CRL_get0_by_cert(crl,&revoked,cert)!=0) return 0;
        }
        if (found != 1) return 0;
    }
    return sk_X509_num(chain)>1;
}

/* Inputs: exact DER request/response/root and concatenated DER CRLs; expected
 * SHA256 imprint, unsigned nonce bytes, numeric policy OID, signer DER SHA256;
 * explicit as-of microseconds and maximum authenticated accuracy. Signature
 * flags are immutable. The parameter is an equality assertion, never a switch.
 * Output [0]=genTime us, [1]=authenticated accuracy us, zeroed on every failure.
 */
EXPORT int cqual_verify_rfc3161(
    const unsigned char *reqbytes,size_t reqlen,
    const unsigned char *respbytes,size_t resplen,
    const unsigned char *rootbytes,size_t rootlen,
    const unsigned char *crlbytes,size_t crllen,
    const unsigned char *imprint,size_t imprintlen,
    const unsigned char *noncebytes,size_t noncelen,
    const char *policy,
    const unsigned char *signer_digest,size_t signer_digest_len,
    int64_t asof_us,int64_t max_accuracy_us,uint32_t asserted_flags,int64_t *out) {
    const unsigned char *p; TS_REQ *req=NULL; TS_RESP *resp=NULL;
    TS_TST_INFO *info; TS_MSG_IMPRINT *mi; TS_VERIFY_CTX *ctx=NULL;
    X509 *root=NULL,*signer=NULL; X509_STORE *store=NULL;
    X509_STORE_CTX *chainctx=NULL; STACK_OF(X509) *chain=NULL;
    STACK_OF(X509_CRL) *crls=NULL; X509_CRL *crl=NULL;
    ASN1_OBJECT *oid=NULL; ASN1_INTEGER *nonce=NULL; BIGNUM *bn=NULL;
    X509_ALGOR *alg; const ASN1_OBJECT *alg_oid;
    unsigned char actual[EVP_MAX_MD_SIZE]; unsigned int actual_len;
    int64_t gen,accuracy,nb,na; int status=Q_INPUT,i;
    if (out) {out[0]=0;out[1]=0;}
    if (!out || !bounded(reqbytes,reqlen) || !bounded(respbytes,resplen) ||
        !bounded(rootbytes,rootlen) || !bounded(crlbytes,crllen) || !imprint || imprintlen!=32 ||
        !bounded(noncebytes,noncelen) || noncelen>32 || noncebytes[0]==0 ||
        !policy || strlen(policy)>128 || !signer_digest || signer_digest_len!=32 ||
        asof_us<0 || max_accuracy_us<0) goto done;
    status=Q_FLAGS;
    if (asserted_flags!=REQUIRED_FLAGS) goto done;
    if (!OPENSSL_init_crypto(OPENSSL_INIT_NO_LOAD_CONFIG | OPENSSL_INIT_NO_ATEXIT,NULL)) goto done;
    status=Q_DER;
    p=reqbytes; req=d2i_TS_REQ(NULL,&p,(long)reqlen); if(!req || p!=reqbytes+reqlen) goto done;
    p=respbytes; resp=d2i_TS_RESP(NULL,&p,(long)resplen); if(!resp || p!=respbytes+resplen) goto done;
    p=rootbytes; root=d2i_X509(NULL,&p,(long)rootlen); if(!root || p!=rootbytes+rootlen) goto done;
    crls=sk_X509_CRL_new_null(); if(!crls) goto done;
    p=crlbytes;
    while(p<crlbytes+crllen) {
        if(sk_X509_CRL_num(crls)>=MAX_CRLS) goto done;
        crl=d2i_X509_CRL(NULL,&p,(long)(crlbytes+crllen-p));
        if(!crl || !sk_X509_CRL_push(crls,crl)) goto done;
        crl=NULL;
    }
    status=Q_REQUEST;
    mi=TS_REQ_get_msg_imprint(req); if(!mi) goto done;
    alg=TS_MSG_IMPRINT_get_algo(mi); if(!alg) goto done;
    X509_ALGOR_get0(&alg_oid,NULL,NULL,alg);
    if(OBJ_obj2nid(alg_oid)!=NID_sha256 ||
        ASN1_STRING_length(TS_MSG_IMPRINT_get_msg(mi))!=32 ||
        CRYPTO_memcmp(ASN1_STRING_get0_data(TS_MSG_IMPRINT_get_msg(mi)),imprint,32)) goto done;
    oid=OBJ_txt2obj(policy,1); bn=BN_bin2bn(noncebytes,(int)noncelen,NULL);
    if(!oid || !bn || !(nonce=BN_to_ASN1_INTEGER(bn,NULL)) ||
        !TS_REQ_get_policy_id(req) || OBJ_cmp(oid,TS_REQ_get_policy_id(req)) ||
        !TS_REQ_get_nonce(req) || ASN1_INTEGER_cmp(nonce,TS_REQ_get_nonce(req)) ||
        TS_REQ_get_version(req)!=1 || TS_REQ_get_ext_count(req)!=0) goto done;
    info=TS_RESP_get_tst_info(resp);
    status=Q_TIME;
    if(!info || !time_us((const ASN1_TIME *)TS_TST_INFO_get_time(info),&gen) || gen<0 || gen>asof_us ||
        TS_TST_INFO_get_ext_count(info)!=0) goto done;
    status=Q_ACCURACY;
    if(!accuracy_us(TS_TST_INFO_get_accuracy(info),max_accuracy_us,&accuracy)) goto done;
    status=Q_SIGNATURE_CHAIN_ESS_EKU;
    store=X509_STORE_new(); if(!store || !X509_STORE_add_cert(store,root)) goto done;
    X509_VERIFY_PARAM_set_time(X509_STORE_get0_param(store),(time_t)(gen/1000000));
    if(!X509_STORE_set_flags(store,X509_V_FLAG_X509_STRICT | X509_V_FLAG_CHECK_SS_SIGNATURE)) goto done;
    ctx=TS_REQ_to_TS_VERIFY_CTX(req,NULL); if(!ctx) goto done;
    /* Regression boundary: conversion deliberately leaves SIGNATURE disabled. */
    if(TS_VERIFY_CTX_add_flags(ctx,REQUIRED_FLAGS)!=REQUIRED_FLAGS) goto done;
    if(!X509_STORE_up_ref(store)) goto done;
    if(!TS_VERIFY_CTX_set0_store(ctx,store)) {X509_STORE_free(store);goto done;}
    if(TS_RESP_verify_response(ctx,resp)!=1 ||
        TS_RESP_verify_signature(TS_RESP_get_token(resp),NULL,store,&signer)!=1) goto done;
    status=Q_SIGNER;
    if(!X509_digest(signer,EVP_sha256(),actual,&actual_len) || actual_len!=32 ||
        CRYPTO_memcmp(actual,signer_digest,32)) goto done;
    chainctx=X509_STORE_CTX_new();
    if(!chainctx || !X509_STORE_CTX_init(chainctx,store,signer,TS_RESP_get_token(resp)->d.sign->cert) ||
        !X509_STORE_CTX_set_purpose(chainctx,X509_PURPOSE_TIMESTAMP_SIGN) || X509_verify_cert(chainctx)!=1 ||
        !(chain=X509_STORE_CTX_get1_chain(chainctx))) goto done;
    for(i=0;i<sk_X509_num(chain);++i) {
        X509 *cert=sk_X509_value(chain,i);
        if(!time_us(X509_get0_notBefore(cert),&nb) || !time_us(X509_get0_notAfter(cert),&na) || gen<nb || gen>na) goto done;
    }
    status=Q_REVOCATION;
    if(!check_crls(chain,crls,asof_us)) goto done;
    out[0]=gen;out[1]=accuracy;status=Q_OK;
done:
    X509_CRL_free(crl); sk_X509_CRL_pop_free(crls,X509_CRL_free);
    sk_X509_pop_free(chain,X509_free); X509_STORE_CTX_free(chainctx);
    X509_free(signer); TS_VERIFY_CTX_free(ctx); X509_STORE_free(store);
    X509_free(root); TS_RESP_free(resp); TS_REQ_free(req);
    ASN1_OBJECT_free(oid); ASN1_INTEGER_free(nonce); BN_free(bn);
    ERR_clear_error(); return status;
}
