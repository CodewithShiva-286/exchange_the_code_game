console.log("hello world");


const vowel=(a)=>{
    let count=0;
    for(let i=0;i<a.length;i++){
        if(a[i]=="a"||a[i]=="e"||a[i]=="i"||a[i]=="o"||a[i]=="u"){
            count++;
        }
}
return count;}

const str = vowel("dfghbtaysuuesvdcg");
console.log(str);
