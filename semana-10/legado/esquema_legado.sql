CREATE TABLE prvmst (prv_id INT PRIMARY KEY, prv_nm TEXT, prv_pais TEXT, prv_dte INT);
CREATE TABLE artmst (art_cd TEXT PRIMARY KEY, art_dsc TEXT, art_lin TEXT, art_cst NUMERIC(12,2), art_ptr INT, art_crt BOOLEAN, art_prv INT);
CREATE TABLE almmst (alm_id INT PRIMARY KEY, alm_dsc TEXT, alm_cdd TEXT);
CREATE TABLE exidet (exi_art TEXT, exi_alm INT, exi_qty INT, exi_fup TIMESTAMPTZ);
CREATE TABLE vtadia (vta_art TEXT, vta_fch DATE, vta_und INT);
CREATE TABLE ocpcab (ocp_id INT PRIMARY KEY, ocp_art TEXT, ocp_qty INT, ocp_sts TEXT, ocp_fcr TIMESTAMPTZ);
