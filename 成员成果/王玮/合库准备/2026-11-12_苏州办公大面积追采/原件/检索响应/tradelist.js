var opt;
var diqu = decodeURIComponent(new ServiceUtil().RequestString("diqu"));
var xmlx = new ServiceUtil().RequestString("xmlx");
var starttime = new ServiceUtil().RequestString("sdt");
var endtime = new ServiceUtil().RequestString("edt");
var keyword = decodeURIComponent(new ServiceUtil().RequestString("wd"));
var categorynumall = '';
var pagesize = 15;
var lj = "";
var myurl = window.location.href;


if(diqu==""){
	diqu="苏州市"
	
}

var curcatenum=$("#curcatenum").val();
var catetypenum="003";
var truecatenum="003";

var timetype="3";

if(curcatenum!="003"&&curcatenum.length==6){
	$("#cate_003").removeClass("active");
	$("#cate_"+curcatenum).addClass("active");
	$(".cate_"+curcatenum).removeClass("hidden");
	truecatenum=curcatenum;
	if(curcatenum=="003001"){
		$(".fbtime").addClass("top155");
	}else{
		$(".fbtime").removeClass("top155");
	}
}

$(document).ready(function() {


	var column = '';
	$('.fbtime').hide();
	
	$('.tab').on('click', 'li', function () {
	    var $this = $(this);
	    var text = $this.text();
	    if (text === '时间区间') {
	        $('.fbtime').show();
			timetype="";
	    } else {
			timetype=$(this).attr("data-timetype");
	        $('.fbtime').hide();
			$("#infodatefrom2").val("");
			$("#infodateto2").val("");
			search2(truecatenum);
	    }
	    $this.addClass('active').siblings().removeClass('active');
	});
	
	$(".catetype").on("click",function(){

		$(".catetype").removeClass("active");
		$(this).addClass("active");
		catetypenum=$(this).attr("data-type");
		if(catetypenum!="003"){
			$(".jytype").addClass("hidden").removeClass("active");
			$(".cate_all").removeClass("hidden").addClass("active");
			$(".cate_"+catetypenum).removeClass("hidden");	
		}else{
			$(".jytype").addClass("hidden").removeClass("active");
			$(".cate_all").removeClass("hidden").addClass("active");
		}
		truecatenum=catetypenum;
		
		if(catetypenum=="003001"){
			$(".fbtime").addClass("top155");
		}else{
			$(".fbtime").removeClass("top155");
		}
		
		//console.log(truecatenum);
		
		xsdt();
		var len = truecatenum.length;
		
			BindGrid3(truecatenum, '0');
		
	})
	
	$(".jytype").on("click",function(){
		$(".jytype").removeClass("active");
		$(this).addClass("active");
		truecatenum=$(this).attr("data-catenum");
		if(truecatenum==""){
			truecatenum=catetypenum;
		}
		xsdt();
		var len = truecatenum.length;
		BindGrid3(truecatenum, '0');
	})



	//地区选择事件
	$("#xiaqutxt").on('change', function(e) {
		//console.log($(this).val());
		var mylocal = $(this).val();
		if (mylocal == "苏州市") {
			$("#suzhou_chosen").attr("style", "display: block;width: 110px;");
			$("#suzhou option").each(function() {
				$(this)[0].selected = false;
			});
			$("#suzhou").trigger("chosen:updated");
		} else {
			$("#suzhou_chosen").attr("style", "display: none;");
		}
	});

	// 判断是否为移动端（手机 + 平板）
function isMobile() {
    // 正则匹配移动端 User-Agent 关键词
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

	$("#xiaqutxt2").on('change', function(e) {
		console.log($(this).val());
		diqu=$(this).val();
		if(diqu=="苏州市"){
			diqu="";
		}
		var mylocal = $(this).val();
		if (mylocal == "苏州市") {
			$("#suzhou2_chosen").attr("style", "width: 110px;");
			$("#suzhou2 option").each(function() {
				$(this)[0].selected = false;
			});
			if(isMobile()){
               $("#suzhou2").show();
			}
			
			$("#suzhou2").trigger("chosen:updated");
		} else {
			$("#suzhou2").hide();
			$("#suzhou2_chosen").attr("style", "display: none;");
		}
		search2(truecatenum)
	});

	$("#suzhou2").on('change', function(e) {
		console.log($(this).val());
		diqu=$(this).val();
		if(diqu=="苏州市"){
			diqu="";
		}
		search2(truecatenum)
	});


	//获取路径
	lj = $("#page").attr("value");
	//获取栏目号
	var categorynum = document.getElementById("categorynum").value;
	//静态部分的序号
	// $("#jt").find(".ewb-trade-tr").each(function() {
	// 	var index = $(this).find("span").html();
	// 	var indexpage = 1;
	// 	indexpage = $("#jt").find(".m-pagination-page .active").find("a").html();
	// 	if(indexpage==undefined)
	// 		indexpage = 1;
	// 	var num = Number(index)+Number((indexpage-1)*15); 
	// 	$(this).find("span").html(num);
	// });
	//初始化
	getZsType();
	getXiaQu(categorynum);
	getZblx();
	getRl();
	//展示搜索条件
	//xstj(categorynum);
	//处理100页以后信息
	var pageindexcz = new ServiceUtil().RequestString("pageIndex"); //100页以后传页码
	if (pageindexcz > 20) {
		xsdt();
		$("#xxList").html("");
		BindGrid(categorynum, pageindexcz);
	} else {
		if (xmlx) {
			xsdt();
			$("#xxList").html("");
			categorynum = xmlx;
			var len = categorynum.length;
			
				$("#titletxt2").val(keyword);
				$("#infodatefrom2").val(starttime);
				$("#infodateto2").val(endtime);
				$("#xiaqutxt2").val(diqu);
				$("#xiaqutxt2_chosen .chosen-single span").html(diqu);
				BindGrid3(categorynum, '0')
		} else {
			xsjt();
		}
	}
	categorynumall = categorynum;
});


function getdate(day){
	if(day==30){
		var myDate=new Date();
		myDate.setMonth(myDate.getMonth()-1);
		var month = myDate.getMonth()+1;
		if(month.toString().length == 1){
			month = "0" + month;
		}
		var date = myDate.getDate();
		if(date.toString().length == 1){
			date = "0"+date;
		}
		return myDate.getFullYear() + "-" + month + "-" + date;
	}else if(day==180){
		var myDate=new Date();
		myDate.setMonth(myDate.getMonth()-3);
		var month = myDate.getMonth()+1;
		if(month.toString().length == 1){
			month = "0" + month;
		}
		var date = myDate.getDate();
		if(date.toString().length == 1){
			date = "0"+date;
		}
		return myDate.getFullYear() + "-" + month + "-" + date;
	}else{
		var myDate=new Date();
		myDate.setDate(myDate.getDate()-day);
		var month = myDate.getMonth()+1;
		if(month.toString().length == 1){
			month = "0" + month;
		}
		var date = myDate.getDate();
		if(date.toString().length == 1){
			date = "0" + date;
		}
		return myDate.getFullYear() + "-" + month + "-" + date;
	}
}

//显示静态
function xsjt() {
	$("#jt").show();
	$("#dt").hide();
}
//显示动态
function xsdt() {
	$("#dt").show();
	$("#jt").hide();
}
//显示搜索条件
function xstj(categorynum) {
	var len = categorynum.length;
	if (len > 3 && categorynum.substring(0, 6) == "003001") {
		//$("#nojsgc").hide();
		$("#jsgc").show();
	} else {
		$("#jsgc").hide();
		//$("#nojsgc").show();
	}
}
//初始化资审类别
function getZsType() {
	$("#zslxtxt").append("<option value=' '>所有</option>");
	$("#zslxtxt").append("<option value='1'>资格预审</option>");
	$("#zslxtxt").append("<option value='2'>资格后审</option>");
	//chosen下拉框
	$("#zslxtxt").chosen({
		disable_search_threshold: 10
	});
}

//初始化地区
function getXiaQu(categorynum) {
	var list = ["苏州市", "工业园区", "吴江区", "常熟市", "太仓市", "昆山市", "张家港"];
	var szlist = ["苏州市区", "吴中区", "相城区", "姑苏区", "高新区", "太湖度假区"];
	// var len=categorynum.length;
	// if(len>3 && (categorynum.substring(0,6)=="003001" || categorynum.substring(0,6)=="003002"))
	// {
	// list=["工业园区","吴江区","常熟市","太仓市","昆山市","张家港","张家港保税区"]
	// }
	//建设
	$("#xiaqutxt").append("<option value=' '>所有</option>");
	$.each(list, function(index, value) {
		if (index == 0) {
			$("#xiaqutxt").append("<option selected = 'selected' value='" + value + "'>" + value + "</option>");
		} else {
			$("#xiaqutxt").append("<option value='" + value + "'>" + value + "</option>");
		}
	});

	$("#suzhou").append("<option value='苏州市 '>所有</option>");
	$.each(szlist, function(index, value) {
		if (index == 0) {
			$("#suzhou").append("<option  value='" + value + "'>" + value + "</option>");
		} else {
			$("#suzhou").append("<option value='" + value + "'>" + value + "</option>");
		}
	});
	//chosen下拉框
	$("#xiaqutxt").chosen({
		disable_search_threshold: 10
	});

	$("#suzhou").chosen({
		disable_search_threshold: 10
	});
	//非建设工程
	//是否是国有产权栏目
	if (myurl.indexOf("tradeinfo_gycq") != -1) {
		$("#xiaqutxt2").append("<option selected = 'selected' value=' '>所有</option>");
		$.each(list, function(index, value) {
			if (index == 0) {
				$("#xiaqutxt2").append("<option  value='" + value + "'>" + value + "</option>");
			} else {
				$("#xiaqutxt2").append("<option value='" + value + "'>" + value + "</option>");
			}

		});
	} else {
		$("#xiaqutxt2").append("<option value=' '>所有</option>");
		$.each(list, function(index, value) {
			if (index == 0) {
				$("#xiaqutxt2").append("<option selected = 'selected' value='" + value + "'>" + value + "</option>");
			} else {
				$("#xiaqutxt2").append("<option value='" + value + "'>" + value + "</option>");
			}

		});
	}



	$("#suzhou2").append("<option value='苏州市 '>所有</option>");
	$.each(szlist, function(index, value) {
		if (index == 0) {
			$("#suzhou2").append("<option  value='" + value + "'>" + value + "</option>");
		} else {
			$("#suzhou2").append("<option value='" + value + "'>" + value + "</option>");
		}
	});
	//chosen下拉框
	$("#xiaqutxt2").chosen({
		disable_search_threshold: 10
	});


	//chosen下拉框
	$("#suzhou2").chosen({
		disable_search_threshold: 10
	});

	if (myurl.indexOf("tradeinfo_gycq") != -1) {
		$("#suzhou2_chosen").attr("style", "display: none;");
	}
}

//初始化招标类型
function getZblx() {
	var list = ["施工招标", "监理招标", "专业招标", "货物招标", "设计招标", "勘察招标", "检测招标", "其他招标"]
	$("#zblxtxt").append("<option value=' '>所有</option>");
	$.each(list, function(index, value) {
		$("#zblxtxt").append("<option value='" + value + "'>" + value + "</option>");
	});
	//chosen下拉框
	$("#zblxtxt").chosen({
		disable_search_threshold: 10
	});
}

//加载时间
function getRl() {
	// 日期选择
	laydate.render({
		elem: '#infodatefrom', //开始日期
		theme: '#4683db',
		done: function(value, date, endDate) { //选择完毕回调

		}
	});
	laydate.render({
		elem: '#infodateto', //结束日期
		theme: '#4683db',
		done: function(value, date, endDate) { //选择完毕回调

		}
	});

	// 计算两年前的日期，作为开始时间的最小可选日期
	var twoYearsAgo = new Date();
	twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);
	var minDate = twoYearsAgo.getFullYear() + '-' + (twoYearsAgo.getMonth() + 1 < 10 ? '0' : '') + (twoYearsAgo.getMonth() + 1) + '-' + (twoYearsAgo.getDate() < 10 ? '0' : '') + twoYearsAgo.getDate();

	laydate.render({
		elem: '#infodatefrom2', //开始日期
		theme: '#4683db',
		min: minDate,
		done: function(value, date, endDate) { //选择完毕回调

		}
	});
	laydate.render({
		elem: '#infodateto2', //结束日期
		theme: '#4683db',
		min: minDate,
		done: function(value, date, endDate) { //选择完毕回调

		}
	});

}


//100页动态分页列表加载
function getdata(obj, indexpage, categorynum) {
	indexpage = indexpage - 1;
	var $pager = $("#pager");
	var url = siteInfo.projectName + "/JyxxSearchAction.action?cmd=getList1";
	var htmltep = $('#info-template').html();
	$.ajax({
		url: url,
		type: "get",
		dataType: "json",
		data: obj,
		success: function(msg) {

			var data = $.parseJSON(msg.custom);
			$("#xxList").html("");
			$.each(data.Table, function(indexs, el) {
				var index = indexs + 1;
				el.index = index + indexpage * pagesize;
			});
			//判断使用模版 
			$("#xxList").append(Mustache.render(htmltep, {
				Table: data.Table
			}));

			//销毁分页  
			if ($pager.pagination()) {
				$pager.pagination('destroy');
			}
			var mytotalnum = $("#mytotalnum").val();

			//分页初始化 
			$pager.pagination({
				pageIndex: indexpage,
				pageSize: pagesize,
				total: mytotalnum,
				debug: true,
				showInfo: true,
				showJump: true,
				showPageSizes: true,
				pageElementSort: ['$page', '$jump']
			});
			//分页按钮点击事件
			$pager.on("pageClicked", function(event, data) {
				BindGrid(categorynum, data.pageIndex);
			}).on('jumpClicked', function(event, data) {
				BindGrid(categorynum, data.pageIndex);
			});


		},
		error: function(msg) {
			alert("没有信息内容！");
			if ($pager.pagination()) {
				$pager.pagination('destroy');
			}
		}
	});
}


function renderPager(indexpage,pagesize,totalCount,categorynum,types){
	var $pager = $("#pager");
	//销毁分页
	if ($pager.pagination()) {
		$pager.pagination('destroy');
	}
	
	var old = indexpage;
	//分页初始化 
	$pager.pagination({
		pageIndex: indexpage,
		pageSize: pagesize,
		total: totalCount,
		debug: true,
		showInfo: true,
		showJump: true,
		showPageSizes: true,
		pageElementSort: ['$page', '$jump']
	});
	//分页按钮点击事件
	$pager.on("pageClicked", function(event, data) {
		if (data.pageIndex < 10) {
			if (types == 2)
				BindGrid2(categorynum, data.pageIndex);
			if (types == 3)
				BindGrid3(categorynum, data.pageIndex);
		} else {
			verify(data.pageIndex, categorynum, old, totalCount, types);
		}
	}).on('jumpClicked', function(event, data) {
		if (data.pageIndex < 10) {
			if (types == 2)
				BindGrid2(categorynum, data.pageIndex);
			if (types == 3)
				BindGrid3(categorynum, data.pageIndex);
		} else {
			verify(data.pageIndex, categorynum, old, totalCount, types);
		}
	});
}

//动态搜索分页列表加载
function getdata2(obj, indexpage, types, categorynum) {
	
	var url = siteInfo.projectName + "/JyxxSearchAction.action?cmd=getList1";
	var htmltep = $('#info-template').html();
	$.ajax({
		url: url,
		type: "get",
		dataType: "json",
		data: obj,
		success: function(msg) {

			var data = $.parseJSON(msg.custom);
			$("#xxList").html("");
			$.each(data.Table, function(indexs, el) {
				var index = indexs + 1;
				el.index = index + indexpage * pagesize;
			});
			//判断使用模版 
			$("#xxList").append(Mustache.render(htmltep, {
				Table: data.Table
			}));

			renderPager(indexpage,pagesize,data.TotalCount,categorynum,types)


		},
		error: function(msg) {
			alert("没有信息内容！");
			if ($pager.pagination()) {
				$pager.pagination('destroy');
			}
		}
	});
}

//条件查询
function search2(categorynum) {
	xsdt();
	if (categorynum == '') {
		categorynum = truecatenum;
	}
	var len = categorynum.length;
	BindGrid3(categorynum, '0');

}

//100页以后调用
function BindGrid(categorynum, indexpage) {
	if (indexpage == 0) {
		window.location.href = "" + lj + "/tradeInfo.html";
	} else if (indexpage < 20) {
		window.location.href = "" + lj + "/" + (indexpage + 1) + ".html";
	} else {
		categorynumall = categorynum;
		var obj = {};
		obj.categorynum = categorynum;
		obj.diqu = "苏州市";
		obj.xmmc = "";
		obj.zstype = "";
		obj.zblx = "";
		obj.starttime = "";
		obj.endtime = "";
		obj.siteguid = siteInfo.siteGuid;
		obj.pageIndex = indexpage - 1;
		obj.pageSize = pagesize;
		getdata(obj, indexpage, categorynum);
	}
}
//建设工程
function BindGrid2(categorynum, indexpage, verify, ImgGuid) {
	var xmmc = $("#titletxt2").val().trim();
	var zstype ="";
	var xiaqu = $("#xiaqutxt_chosen .chosen-single span").html();
	if (xiaqu == "所有") {
		xiaqu = "";
	}
	if (xiaqu == "苏州市") {
		xiaqu = $("#suzhou_chosen .chosen-single span").html();
		if (xiaqu == "所有") {
			xiaqu = "苏州市";
		}
	}
	var zblx ="";
	var starttime = $("#infodatefrom").val();
	var endtime = $("#infodateto").val();
	var jyfl="";
	categorynumall = categorynum;
	var obj = {};
	obj.categorynum = categorynum;
	obj.diqu = xiaqu;
	obj.xmmc = xmmc;
	obj.zstype = zstype;
	obj.zblx = zblx;
	obj.jyfl = jyfl;
	obj.starttime = starttime;
	obj.endtime = endtime;
	obj.siteguid = siteInfo.siteGuid;
	obj.pageIndex = indexpage;
	obj.pageSize = pagesize;
	obj.YZM = verify;
	obj.ImgGuid = ImgGuid;
	getdata2(obj, indexpage, 2, categorynum);
}
//非建设工程
function BindGrid3(categorynum, indexpage, verify, ImgGuid) {
	var xmmc = $("#titletxt2").val().trim();
	var zstype = "";
	// var xiaqu = $("#xiaqutxt2_chosen .chosen-single span").html();
	// if (xiaqu == "所有") {
	// 	xiaqu = "";
	// }
	// if (xiaqu == "苏州市") {
	// 	xiaqu = $("#suzhou2_chosen .chosen-single span").html();
	// 	if (xiaqu == "所有") {
	// 		xiaqu = "苏州市";
	// 	}
	// }
	if(diqu=="苏州市 "){
			diqu="苏州市";
	}
	xiaqu=diqu;
	var zblx = "";

	var starttime = $("#infodatefrom2").val();
	var endtime = $("#infodateto2").val();
	if(timetype==""){
		// 时间区间：使用用户自定义的日期，如果未填写则默认近两年
		if(!starttime){
			starttime = getdate(730);
		}
		if(!endtime){
			endtime = getdate(0);
		}
	}else{
		starttime = getdate(timetype);
		endtime = getdate(0);
	}
	var jyfl=$("#jyfltxt").val();
	categorynumall = categorynum;
	var obj = {};
	obj.categorynum = categorynum;
	obj.diqu = xiaqu;
	obj.xmmc = xmmc;
	obj.zstype = zstype;
	obj.zblx = zblx;
	obj.jyfl = jyfl;
	obj.starttime = starttime;
	obj.endtime = endtime;
	obj.siteguid = siteInfo.siteGuid;
	obj.pageIndex = indexpage;
	obj.pageSize = pagesize;
	obj.YZM = verify;
	obj.ImgGuid = ImgGuid;
	getdata2(obj, indexpage, 3, categorynum);
}



function verify(pageIndex, categorynum, oldindex, total, types,isjt) {
	var jz = layer.open({
		title: '验证码',
		type: 2,
		content: '/pageVerify.html',
		area: ['400px', '200px'],
		btn: ['确定'],
		yes: function(index, layero) {
			var body = layer.getChildFrame('body', index);
			var verify = body.find('#yzm').val();
			var ImgGuid = body.find('#imgguid').val();
			if (verify == '') {
				layer.msg('验证码为空!');
			} else {
				webbuilder.pageListVerify(ImgGuid, verify, function(msg) {
					if (msg.message == null || msg.message == "") {
						layer.close(jz);
						$("#dt").show();
						$("#jt").hide();
						if (types == 2)
							BindGrid2(categorynum, pageIndex, verify, ImgGuid);
						if (types == 3)
							BindGrid3(categorynum, pageIndex, verify, ImgGuid);
					} else {
						layer.msg(msg.message);
						body.find('#yzm').val("");
					}
				})
			}
		},
		cancel: function(index, layero) {
			if(isjt==1){
				$("#dt").show();
				$("#jt").hide();
				if (types == 2)
					BindGrid2(categorynum, oldindex);
				if (types == 3)
					BindGrid3(categorynum, oldindex);
			}else{
				renderPager(oldindex,pagesize,total,categorynum,types);
			}
			
			
			//renderPager(oldindex,pageSize,total);
			//console.log(oldindex);
		}
	});
}
